"""Solicitud de acciones sobre el relé, compartida por el panel, el programador y el
recordatorio. Comprobar estado y reservar el relé es atómico (sin `await`)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum

from .config import Config
from .events import EventBus
from .power import Action, PowerMachine
from .relay import Relay, RelayBusy

log = logging.getLogger("pc-power.control")


class Outcome(str, Enum):
    ACCEPTED = "accepted"
    BUSY = "busy"
    INVALID_STATE = "invalid_state"


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    pulse_ms: int = 0
    state: str = ""


class PowerController:
    def __init__(self, cfg: Config, relay: Relay, machine: PowerMachine, bus: EventBus):
        self._cfg, self._relay, self._machine, self._bus = cfg, relay, machine, bus
        self.tasks: set[asyncio.Task] = set()

    def request(self, act: Action, source: str, ip: str | None = None) -> Result:
        if self._relay.busy:
            return Result(Outcome.BUSY)
        if not self._machine.allowed(act):
            return Result(Outcome.INVALID_STATE, state=self._machine.state.value)
        ms = self._cfg.long_pulse_ms if act is Action.FORCE_OFF else self._cfg.short_pulse_ms
        try:
            task = self._relay.start(ms / 1000)
        except RelayBusy:
            return Result(Outcome.BUSY)
        self._machine.on_action_started(act)
        self.tasks.add(task)

        def _done(t: asyncio.Task) -> None:
            self.tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                log.error("fallo durante el pulso: %r", t.exception())

        task.add_done_callback(_done)
        log.info("acción %s aceptada desde %s (pulso %d ms)", act.value, source, ms)
        self._bus.emit("action_accepted", action=act.value, source=source, ip=ip)
        return Result(Outcome.ACCEPTED, pulse_ms=ms)

    def shutdown(self) -> None:
        for t in list(self.tasks):
            t.cancel()
