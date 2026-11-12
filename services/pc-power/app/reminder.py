"""Recordatorio de apagado (design D8 y D9).

Si el PC lleva `REMINDER_AFTER_H` horas encendido sin interrupción, avisa por ntfy con dos
botones: **Apagar** (apagado normal) y **Mantener encendido** (descarte). Mientras siga
encendido repite el aviso a las horas fijas `REMINDER_TIMES`, sin duplicar si hubo otro hace
menos de 30 minutos.

Cada aviso lleva un enlace secreto de un solo uso (solo se guarda su hash) que permite
únicamente el apagado normal o el descarte, nunca el panel ni otra acción.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .config import Config
from .control import Outcome, PowerController
from .events import EventBus
from .notifier import Notifier
from .power import Action, PowerMachine, State

log = logging.getLogger("pc-power.reminder")

MIN_GAP_S = 30 * 60        # no se repite un aviso si hubo otro hace menos de 30 minutos
TOKEN_TTL_S = 12 * 3600    # un enlace caduca con el siguiente aviso o a las 12 h
RATE_PER_MIN = 10          # peticiones a /r/ por minuto (el exceso recibe 404)
TICK_S = 15.0


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def fmt_hours(seconds: float) -> str:
    minutes = int(seconds // 60)
    h, m = divmod(minutes, 60)
    return f"{h} h {m} min" if m else f"{h} h"


class Reminders:
    def __init__(
        self,
        cfg: Config,
        machine: PowerMachine,
        notifier: Notifier,
        controller: PowerController,
        bus: EventBus,
        path: Path,
        clock: Callable[[], float] = time.time,
    ):
        self._cfg, self._machine, self._notifier = cfg, machine, notifier
        self._controller, self._bus = controller, bus
        self._path = Path(path)
        self._clock = clock
        self._tz = ZoneInfo(cfg.tz)
        self.on_since: float | None = None
        self.first_sent = False
        self.last_sent: float | None = None
        self._last_tick = clock()
        self._hits: deque[float] = deque()
        self._tokens: dict[str, dict] = {}
        bus.subscribe(self._on_event)
        self._load()

    # ---- estado: cuánto lleva encendido ---------------------------------------------
    def _on_event(self, event: dict) -> None:
        if event["type"] != "state_change":
            return
        if event.get("new") == "on" and self.on_since is None:
            self.on_since = event["ts"]
        elif event.get("new") == "off":
            self.on_since, self.first_sent, self.last_sent = None, False, None

    # ---- reloj ----------------------------------------------------------------------
    async def run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                log.exception("fallo en el recordatorio")
            await asyncio.sleep(TICK_S)

    def tick(self) -> None:
        now = self._clock()
        last_tick, self._last_tick = self._last_tick, now
        if not self._notifier.enabled or self.on_since is None or self._machine.state is not State.ON:
            return  # apagado, en transición o sin estado fiable: no se recuerda nada
        elapsed = now - self.on_since
        if not self.first_sent:
            if elapsed >= self._cfg.reminder_after_h * 3600:
                self._send(now, elapsed)
            return
        if self._crossed_fixed_time(last_tick, now) and now - (self.last_sent or 0) >= MIN_GAP_S:
            self._send(now, elapsed)

    def _crossed_fixed_time(self, start: float, end: float) -> bool:
        """¿Alguna de las horas fijas cayó en (start, end]? (en la zona horaria configurada)"""
        day = datetime.fromtimestamp(end, self._tz).date()
        for back in (1, 0):
            d = day - timedelta(days=back)
            for h, m in self._cfg.reminder_times:
                ts = datetime(d.year, d.month, d.day, h, m, tzinfo=self._tz).timestamp()
                if start < ts <= end:
                    return True
        return False

    # ---- envío ------------------------------------------------------------------------
    def _send(self, now: float, elapsed: float) -> None:
        for entry in self._tokens.values():  # caducan los enlaces de avisos anteriores
            entry["exp"] = min(entry["exp"], now)
        token = secrets.token_urlsafe(32)
        self._tokens[_hash(token)] = {"exp": now + TOKEN_TTL_S, "used": False}
        self._purge(now)
        self._save()

        actions = None
        if self._cfg.public_url:
            prefix = self._cfg.cookie_path if self._cfg.cookie_path.endswith("/") else self._cfg.cookie_path + "/"
            base = f"{self._cfg.public_url}{prefix}r/{token}"
            actions = [
                {"action": "http", "label": "Apagar", "url": f"{base}/off", "method": "POST", "clear": True},
                {"action": "http", "label": "Mantener encendido", "url": f"{base}/keep", "method": "POST", "clear": True},
            ]
        self._notifier.send(
            f"¿Apagar {self._cfg.pc_name}?",
            f"{self._cfg.pc_name} lleva {fmt_hours(elapsed)} encendido. ¿Quieres apagarlo?",
            tags=["bulb"], priority=3, actions=actions,
        )
        self.first_sent, self.last_sent = True, now
        self._bus.emit("reminder_sent", hours=round(elapsed / 3600, 1))

    # ---- enlaces de un solo uso -----------------------------------------------------------
    def rate_ok(self) -> bool:
        now = self._clock()
        while self._hits and now - self._hits[0] >= 60:
            self._hits.popleft()
        if len(self._hits) >= RATE_PER_MIN:
            return False
        self._hits.append(now)
        return True

    def consume(self, token: str, kind: str, ip: str | None = None) -> int:
        """Aplica un enlace. Devuelve 204 (hecho), 409 (relé ocupado: el enlace sigue vivo) o 404."""
        now = self._clock()
        entry = self._tokens.get(_hash(token))
        if entry is None or entry["used"] or entry["exp"] <= now:
            return 404
        if kind == "keep":
            entry["used"] = True
            self._save()
            self._bus.emit("reminder_keep")
            return 204
        if kind != "off":
            return 404
        res = self._controller.request(Action.SOFT_OFF, "reminder", ip)
        if res.outcome is Outcome.BUSY:
            return 409
        entry["used"] = True
        self._save()
        if res.outcome is Outcome.ACCEPTED:
            self._bus.emit("reminder_off")
        return 204  # PC ya apagado: no se acciona el relé y no hay nada más que hacer

    # ---- persistencia (solo hashes) ------------------------------------------------------------
    def _purge(self, now: float) -> None:
        self._tokens = {h: e for h, e in self._tokens.items() if e["exp"] > now - 86400}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"tokens": self._tokens}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            tokens = data.get("tokens", {})
        except (OSError, ValueError, AttributeError):
            return
        now = self._clock()
        if isinstance(tokens, dict):
            self._tokens = {
                h: {"exp": float(e["exp"]), "used": bool(e.get("used"))}
                for h, e in tokens.items()
                if isinstance(h, str) and isinstance(e, dict) and isinstance(e.get("exp"), (int, float))
                and e["exp"] > now - 86400
            }
