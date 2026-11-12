"""Notificaciones push por ntfy (design D3).

Cola acotada y una tarea consumidora: enviar nunca bloquea las acciones, el acceso ni el
monitoreo. Sin NTFY_URL no existe ningún envío. Los mensajes solo usan campos de los
eventos (nunca códigos, tokens ni cookies).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
from collections import deque
from datetime import datetime
from typing import Callable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .history import ACTION_ES, SOURCE_ES

log = logging.getLogger("pc-power.notifier")

PostFn = Callable[[str, dict, str], None]
RESULT_TEXT = {
    "normal": "El PC se apagó con normalidad.",
    "forced": "El PC no se apagó solo y hubo que forzar el apagado.",
    "failed": "El PC sigue encendido incluso tras forzar el apagado.",
}
# Pasos internos del apagado programado: su resultado se avisa una sola vez, al final
QUIET_SOURCES = ("schedule_off", "schedule_force")


def default_post(server: str, payload: dict, token: str, timeout: float = 5.0) -> None:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(server, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL validada en la configuración
        resp.read()


class Notifier:
    def __init__(
        self,
        url: str,
        token: str = "",
        tz: str = "America/Bogota",
        post: PostFn = default_post,
        clock: Callable[[], float] = time.time,
        max_per_hour: int = 20,
        queue_max: int = 50,
        suppress_no_effect: Callable[[], bool] = lambda: False,
    ):
        self.enabled = bool(url)
        u = urlparse(url) if url else None
        self._server = f"{u.scheme}://{u.netloc}" if u else ""
        self._topic = u.path.strip("/") if u else ""
        self._token = token
        self._tz = ZoneInfo(tz)
        self._post = post
        self._clock = clock
        self._max = max_per_hour
        self._sent: deque[float] = deque()
        self._suppress_no_effect = suppress_no_effect
        self._queue: asyncio.Queue | None = None
        self._queue_max = queue_max
        self.dropped = 0

    # ---- entrada: eventos del bus --------------------------------------------
    def handle(self, event: dict) -> None:
        if not self.enabled:
            return
        msg = self._message_for(event)
        if msg:
            self.send(**msg)

    def send(self, title: str, message: str, *, tags: list[str] | None = None,
             priority: int | None = None, actions: list[dict] | None = None) -> bool:
        """Encola un aviso. Devuelve False si se descartó (límite horario o cola llena)."""
        if not self.enabled:
            return False
        now = self._clock()
        while self._sent and now - self._sent[0] >= 3600:
            self._sent.popleft()
        if len(self._sent) >= self._max:
            self.dropped += 1
            log.warning("límite de avisos por hora alcanzado; se descarta: %s", title)
            return False
        payload: dict = {"topic": self._topic, "title": title, "message": message}
        if tags:
            payload["tags"] = tags
        if priority:
            payload["priority"] = priority
        if actions:
            payload["actions"] = actions
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._queue_max)
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            self.dropped += 1
            log.warning("cola de avisos llena; se descarta: %s", title)
            return False
        self._sent.append(now)
        return True

    # ---- consumidor ---------------------------------------------------------
    async def run(self) -> None:
        if self._queue is None:
            self._queue = asyncio.Queue(maxsize=self._queue_max)
        while True:
            payload = await self._queue.get()
            try:
                await asyncio.to_thread(self._post, self._server, payload, self._token)
            except Exception as exc:  # noqa: BLE001 - un fallo de red nunca afecta al control
                log.warning("no se pudo enviar el aviso «%s»: %r", payload.get("title"), exc)
            finally:
                self._queue.task_done()

    async def drain(self) -> None:
        """Espera a que se envíe todo lo encolado (pruebas)."""
        if self._queue is not None:
            await self._queue.join()

    # ---- contenido ----------------------------------------------------------
    def _hora(self, ts: float) -> str:
        return datetime.fromtimestamp(ts, self._tz).strftime("%d/%m %H:%M")

    def _message_for(self, e: dict) -> dict | None:
        t = e["type"]
        if t == "action_accepted":
            if e.get("source") in QUIET_SOURCES:
                return None
            action = ACTION_ES.get(e.get("action"), e.get("action"))
            return {"title": "Acción enviada", "message": f"{action} · {SOURCE_ES.get(e.get('source'), 'Panel')}", "tags": ["zap"]}
        if t == "no_effect":
            if self._suppress_no_effect():
                return None
            action = ACTION_ES.get(e.get("action"), e.get("action"))
            return {"title": "Sin efecto", "message": f"La acción «{action}» no surtió efecto: el PC no cambió de estado.",
                    "tags": ["warning"], "priority": 4}
        if t == "login_ok":
            return {"title": "Navegador nuevo autorizado", "message": f"{self._hora(e['ts'])} · IP {e.get('ip', '?')}",
                    "tags": ["key"], "priority": 4}
        if t == "lockout":
            return {"title": "Bloqueo por intentos fallidos", "message": f"IP {e.get('ip', '?')} · {e.get('attempts')} intentos",
                    "tags": ["rotating_light"], "priority": 4}
        if t == "scheduled_off_result":
            result = e.get("result")
            return {"title": "Apagado programado", "message": RESULT_TEXT.get(result, str(result)),
                    "tags": ["warning"] if result != "normal" else ["white_check_mark"],
                    "priority": 4 if result == "failed" else None}
        return None
