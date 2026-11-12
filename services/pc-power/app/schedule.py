"""Programador de un encendido y un apagado únicos (design D5 y D7).

Una sola tarea con `tick()` cada segundo (determinista y fácil de probar con reloj simulado).
Estado persistente en `schedule.json`. El apagado programado envía el pulso corto y, si el PC
sigue encendido tras `OFF_FORCE_AFTER_MIN`, el largo; nunca fuerza si el PC llegó a apagarse.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .config import Config
from .control import Outcome, PowerController
from .events import EventBus
from .power import Action, PowerMachine, State

log = logging.getLogger("pc-power.schedule")

HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
STALE_S = 300.0   # una programación vencida hace más de 5 min no se ejecuta
RETRY_S = 10.0    # un único reintento si el relé estaba ocupado


class ScheduleError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def next_occurrence(hhmm: str, now: float, tz: ZoneInfo) -> float:
    """Próxima ocurrencia de HH:MM (hora de `tz`) estrictamente posterior a `now` (< 24 h)."""
    m = HHMM.match(hhmm.strip()) if isinstance(hhmm, str) else None
    if not m:
        raise ScheduleError("invalid_time")
    dt = datetime.fromtimestamp(now, tz)
    cand = dt.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
    if cand <= dt + timedelta(seconds=5):
        cand += timedelta(days=1)
    return cand.timestamp()


class Scheduler:
    def __init__(
        self,
        cfg: Config,
        machine: PowerMachine,
        controller: PowerController,
        bus: EventBus,
        path: Path,
        clock: Callable[[], float] = time.time,
        retry_s: float = RETRY_S,
        stale_s: float = STALE_S,
    ):
        self._cfg, self._machine, self._controller, self._bus = cfg, machine, controller, bus
        self._path = Path(path)
        self._clock = clock
        self._tz = ZoneInfo(cfg.tz)
        self._force_s = cfg.off_force_after_min * 60
        self._retry_s, self._stale_s = retry_s, stale_s
        self.on_at: float | None = None
        self.off_at: float | None = None
        self.off_wait: dict | None = None  # {deadline, phase: soft|forced, fd, retry_at}
        self._retry: dict[str, float] = {}  # kind -> momento del reintento
        self._quiet_until = 0.0
        bus.subscribe(self._on_event)
        self._load()

    # ---- consulta ---------------------------------------------------------------
    @property
    def waiting(self) -> bool:
        """Hay una espera de forzado en curso (el notificador silencia el 'sin efecto')."""
        return self.off_wait is not None

    @property
    def quiet(self) -> bool:
        """El notificador no avisa de 'sin efecto' durante la espera ni justo después de ella:
        el resultado del apagado programado se avisa una sola vez, al terminar."""
        return self.off_wait is not None or self._clock() < self._quiet_until

    def _label(self, ts: float | None) -> str | None:
        return datetime.fromtimestamp(ts, self._tz).strftime("%H:%M") if ts else None

    def status(self) -> dict:
        now = self._clock()
        wait = None
        if self.off_wait:
            wait = {"phase": self.off_wait["phase"], "force_label": self._label(self.off_wait["deadline"])}
        return {
            "on": self._label(self.on_at),
            "off": self._label(self.off_at),
            "off_wait": wait,
            "now": now,
            "tz": self._cfg.tz,
        }

    # ---- API ---------------------------------------------------------------------
    def set(self, kind: str, hhmm: str) -> dict:
        if kind not in ("on", "off"):
            raise ScheduleError("invalid_kind")
        at = next_occurrence(hhmm, self._clock(), self._tz)
        if kind == "on" and self._machine.state is not State.OFF:
            raise ScheduleError("invalid_state")
        if kind == "off" and (self._machine.state is not State.ON or self.off_wait):
            raise ScheduleError("invalid_state")
        if kind == "on":
            self.on_at = at
        else:
            self.off_at = at
        self._retry.pop(kind, None)
        self._save()
        self._bus.emit("schedule_set", kind=kind)
        return self.status()

    def cancel(self, kind: str) -> bool:
        if kind not in ("on", "off"):
            raise ScheduleError("invalid_kind")
        changed = False
        if kind == "on":
            changed, self.on_at = self.on_at is not None, None
        else:
            changed = self.off_at is not None or self.off_wait is not None
            self.off_at, self.off_wait = None, None
        self._retry.pop(kind, None)
        if changed:
            self._save()
            self._bus.emit("schedule_cancelled", kind=kind)
        return changed

    # ---- reloj ---------------------------------------------------------------------
    async def run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - el programador nunca debe morir
                log.exception("fallo en el programador")
            await asyncio.sleep(1)

    def tick(self) -> None:
        now = self._clock()
        self._tick_on(now)
        self._tick_off(now)
        self._tick_wait(now)

    def _stale(self, now: float, at: float) -> bool:
        return now - at > self._stale_s

    def _tick_on(self, now: float) -> None:
        if self.on_at is None or now < self.on_at or self._retry_wait("on", now):
            return
        state = self._machine.state
        if state is State.CHECKING and not self._stale(now, self.on_at):
            return  # aún sin estado fiable: se espera
        if state is State.OFF:
            res = self._controller.request(Action.POWER_ON, "schedule")
            if res.outcome is Outcome.BUSY and self._schedule_retry("on", now):
                return
            if res.outcome is Outcome.ACCEPTED:
                self.on_at = None
                self._save()
                self._bus.emit("schedule_fired", kind="on")
                return
        self._discard("on")

    def _tick_off(self, now: float) -> None:
        if self.off_at is None or now < self.off_at or self._retry_wait("off", now):
            return
        state = self._machine.state
        if state is State.CHECKING and not self._stale(now, self.off_at):
            return
        if state is State.ON:
            res = self._controller.request(Action.SOFT_OFF, "schedule_off")
            if res.outcome is Outcome.BUSY and self._schedule_retry("off", now):
                return
            if res.outcome is Outcome.ACCEPTED:
                self.off_at = None
                self.off_wait = {"deadline": now + self._force_s, "phase": "soft", "fd": None, "started": now}
                self._save()
                self._bus.emit("schedule_fired", kind="off")
                return
        self._discard("off")

    def _tick_wait(self, now: float) -> None:
        w = self.off_wait
        if w is None:
            return
        if w["phase"] == "soft" and now >= w["deadline"]:
            if self._retry_wait("force", now):
                return
            if self._machine.state in (State.ON, State.STOPPING):
                res = self._controller.request(Action.FORCE_OFF, "schedule_force")
                if res.outcome is Outcome.BUSY and self._schedule_retry("force", now):
                    return
                if res.outcome is Outcome.ACCEPTED:
                    w["phase"], w["fd"] = "forced", now + self._cfg.transition_timeout_s
                    self._save()
                    return
                self._finish("failed")
            else:
                self._finish("normal")
        elif w["phase"] == "forced" and w["fd"] is not None and now >= w["fd"]:
            self._finish("failed")

    def _finish(self, result: str) -> None:
        self.off_wait = None
        self._quiet_until = self._clock() + 30
        self._retry.pop("force", None)
        self._save()
        self._bus.emit("scheduled_off_result", result=result)

    def _discard(self, kind: str) -> None:
        if kind == "on":
            self.on_at = None
        else:
            self.off_at = None
        self._retry.pop(kind, None)
        self._save()
        self._bus.emit("schedule_discarded", kind=kind)

    # ---- reintento único si el relé está ocupado ----------------------------------------------
    def _schedule_retry(self, key: str, now: float) -> bool:
        if key in self._retry:
            self._retry.pop(key)
            return False  # ya se reintentó una vez
        self._retry[key] = now + self._retry_s
        return True

    def _retry_wait(self, key: str, now: float) -> bool:
        return key in self._retry and now < self._retry[key]

    # ---- eventos del bus -----------------------------------------------------------------------
    def _on_event(self, event: dict) -> None:
        w = self.off_wait
        if w is None:
            return
        t = event["type"]
        if t == "state_change" and event.get("new") == "off":
            self._finish("normal" if w["phase"] == "soft" else "forced")
        elif t == "action_accepted" and event.get("source") in ("panel", "reminder"):
            self.off_wait = None  # el usuario tomó el control: se cancela la espera de forzado
            self._save()
            self._bus.emit("schedule_cancelled", kind="off")

    # ---- persistencia ----------------------------------------------------------------------------
    def _save(self) -> None:
        data = {"on": self.on_at, "off": self.off_at, "off_wait": self.off_wait}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        now = self._clock()

        def num(v):
            return float(v) if isinstance(v, (int, float)) else None

        on_at, off_at = num(data.get("on")), num(data.get("off"))
        for kind, at in (("on", on_at), ("off", off_at)):
            if at is not None and self._stale(now, at):
                self._bus.emit("schedule_discarded", kind=kind)
                at = None
            if kind == "on":
                self.on_at = at
            else:
                self.off_at = at
        w = data.get("off_wait")
        if isinstance(w, dict) and num(w.get("deadline")) is not None and w.get("phase") in ("soft", "forced"):
            limit = num(w.get("fd")) if w["phase"] == "forced" and num(w.get("fd")) else num(w["deadline"])
            if now - limit <= self._stale_s:
                self.off_wait = {"deadline": num(w["deadline"]), "phase": w["phase"], "fd": num(w.get("fd")),
                                 "started": num(w.get("started")) or now}
            else:
                self._bus.emit("schedule_discarded", kind="off")
        self._save()
