"""Bus de eventos interno mínimo (design D1).

El control básico emite eventos; el historial, el notificador, el programador y el
recordatorio los consumen. Un suscriptor que falla nunca interrumpe a quien emite.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

log = logging.getLogger("pc-power.events")

Subscriber = Callable[[dict], None]


class EventBus:
    def __init__(self, clock: Callable[[], float] = time.time):
        self._subs: list[Subscriber] = []
        self._clock = clock

    def subscribe(self, fn: Subscriber) -> None:
        self._subs.append(fn)

    def emit(self, type: str, **data) -> dict:
        event = {"ts": self._clock(), "type": type, **data}
        for fn in list(self._subs):
            try:
                fn(event)
            except Exception:  # noqa: BLE001 - aislar a los suscriptores
                log.exception("suscriptor falló con el evento %s", type)
        return event
