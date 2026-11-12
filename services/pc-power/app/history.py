"""Historial de actividad en JSON Lines con rotación (design D2).

Solo se guardan campos de una lista blanca: nunca códigos, tokens ni cookies.
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from pathlib import Path
from typing import Callable

ALLOWED = ("ip", "action", "source", "old", "new", "external", "attempts", "kind", "result", "hours")
STATE_ES = {"on": "encendido", "off": "apagado", "starting": "encendiendo", "stopping": "apagando", "checking": "comprobando"}
ACTION_ES = {"power_on": "Encender", "soft_off": "Apagar", "force_off": "Forzar apagado"}
SOURCE_ES = {
    "panel": "Desde el panel",
    "schedule": "Programado",
    "schedule_off": "Programado",
    "schedule_force": "Programado (forzado de respaldo)",
    "reminder": "Desde el recordatorio",
}
KIND_ES = {"on": "encendido", "off": "apagado"}
RESULT_ES = {"normal": "apagado normal", "forced": "hubo que forzarlo", "failed": "el PC sigue encendido"}
RECORDED_STATES = ("on", "off")


def describe(rec: dict) -> str:
    t = rec["type"]
    ip = f" · IP {rec['ip']}" if rec.get("ip") else ""
    if t == "action_accepted":
        return f"{SOURCE_ES.get(rec.get('source'), 'Acción')}: {ACTION_ES.get(rec.get('action'), rec.get('action'))}{ip}"
    if t == "state_change":
        ext = " (externo, no provocado desde aquí)" if rec.get("external") else ""
        return f"PC {STATE_ES.get(rec.get('new'), rec.get('new'))}{ext}"
    if t == "no_effect":
        return f"La acción «{ACTION_ES.get(rec.get('action'), rec.get('action'))}» no surtió efecto"
    if t == "login_ok":
        return f"Navegador nuevo autorizado{ip}"
    if t == "logout":
        return "Sesión cerrada"
    if t == "logout_all":
        return "Todas las sesiones cerradas"
    if t == "lockout":
        return f"Bloqueo por intentos fallidos{ip} ({rec.get('attempts')} intentos)"
    if t.startswith("schedule_"):
        what = KIND_ES.get(rec.get("kind"), "")
        verb = {"set": "programado", "fired": "ejecutado", "discarded": "descartado", "cancelled": "cancelado"}.get(t[9:], t[9:])
        return f"{what.capitalize()} {verb}"
    if t == "scheduled_off_result":
        return f"Apagado programado: {RESULT_ES.get(rec.get('result'), rec.get('result'))}"
    if t == "reminder_sent":
        return f"Recordatorio enviado ({rec.get('hours')} h encendido)" if rec.get("hours") else "Recordatorio enviado"
    if t == "reminder_off":
        return "Apagado solicitado desde el recordatorio"
    if t == "reminder_keep":
        return "Recordatorio descartado: mantener encendido"
    return t


class History:
    def __init__(
        self,
        path: Path,
        max_events: int = 1000,
        rotate_at: int = 1200,
        external_window_s: float = 120.0,
        clock: Callable[[], float] = time.time,
    ):
        self._path = Path(path)
        self._max = max_events
        self._rotate_at = rotate_at
        self._window = external_window_s
        self._clock = clock
        self._events: deque[dict] = deque(maxlen=max_events)
        self._file_lines = 0
        self._last_action_ts: float | None = None
        self._load()

    # ---- suscriptor del bus -----------------------------------------------
    def handle(self, event: dict) -> None:
        t = event["type"]
        if t == "action_accepted":
            self._last_action_ts = event["ts"]
        if t == "state_change" and event.get("new") not in RECORDED_STATES:
            return
        if t == "state_change":
            recent = self._last_action_ts is not None and event["ts"] - self._last_action_ts <= self._window
            event = {**event, "external": not recent}
        rec = {"ts": event["ts"], "type": t}
        for k in ALLOWED:
            if k in event and event[k] is not None:
                rec[k] = event[k]
        self._append(rec)

    # ---- consulta -----------------------------------------------------------
    def recent(self, limit: int = 50) -> list[dict]:
        items = list(self._events)[-limit:][::-1]
        return [{**r, "text": describe(r)} for r in items]

    def __len__(self) -> int:
        return len(self._events)

    # ---- persistencia ---------------------------------------------------------
    def _load(self) -> None:
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            try:
                rec = json.loads(line)
                if isinstance(rec, dict) and "type" in rec and "ts" in rec:
                    self._events.append(rec)
            except ValueError:
                continue
        self._file_lines = len(lines)

    def _append(self, rec: dict) -> None:
        self._events.append(rec)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._file_lines += 1
        if self._file_lines > self._rotate_at:
            self._rotate()

    def _rotate(self) -> None:
        tmp = self._path.with_name(self._path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for rec in self._events:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)
        self._file_lines = len(self._events)
