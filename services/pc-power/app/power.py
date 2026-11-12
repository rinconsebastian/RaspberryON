"""Máquina de estados del PC (design D4).

Estado detectado por ping: checking -> on | off.
Estados de transición tras una acción: starting, stopping.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Callable


class State(str, Enum):
    CHECKING = "checking"
    OFF = "off"
    ON = "on"
    STARTING = "starting"
    STOPPING = "stopping"


class Action(str, Enum):
    POWER_ON = "power_on"
    SOFT_OFF = "soft_off"
    FORCE_OFF = "force_off"


# Estados en los que cada acción es válida (design D4)
ALLOWED: dict[Action, frozenset[State]] = {
    Action.POWER_ON: frozenset({State.OFF}),
    Action.SOFT_OFF: frozenset({State.ON}),
    Action.FORCE_OFF: frozenset({State.ON, State.OFF, State.STOPPING}),
}

NOTICE_TTL_S = 30.0


class PowerMachine:
    def __init__(
        self,
        transition_timeout_s: float = 120.0,
        fail_threshold: int = 3,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ):
        self._timeout = transition_timeout_s
        self._threshold = fail_threshold
        self._clock = clock
        self._wall = wall

        self._detected = State.CHECKING
        self._fails = 0
        self._transition: State | None = None  # STARTING / STOPPING
        self._transition_started = 0.0
        self._transition_action: Action | None = None
        self._since = wall()
        self._notice: tuple[str, Action | None, float] | None = None  # (code, action, wall_ts)
        self._last_effective = State.CHECKING
        # Gancho opcional hacia el bus de eventos: emit(tipo, **datos)
        self.emit: Callable[..., object] = lambda *a, **k: None

    # ---- lectura -------------------------------------------------------
    @property
    def state(self) -> State:
        return self._transition or self._detected

    def allowed(self, action: Action) -> bool:
        return self.state in ALLOWED[action]

    def snapshot(self) -> dict:
        self._expire_transition()
        notice = None
        if self._notice:
            code, action, ts = self._notice
            if self._wall() - ts <= NOTICE_TTL_S:
                notice = {"code": code, "action": action.value if action else None}
            else:
                self._notice = None
        return {
            "state": self.state.value,
            "since": self._since,
            "now": self._wall(),
            "notice": notice,
        }

    # ---- eventos -------------------------------------------------------
    def on_ping(self, ok: bool) -> None:
        if ok:
            self._fails = 0
            self._detected = State.ON
        else:
            self._fails += 1
            if self._fails >= self._threshold:
                self._detected = State.OFF
        self._resolve_transition()
        self._expire_transition()
        self._mark_change()

    def on_action_started(self, action: Action) -> None:
        """El relé aceptó un pulso. Abre la transición que corresponda."""
        prev = self.state
        self._notice = None
        if action is Action.POWER_ON and prev is State.OFF:
            self._begin(State.STARTING, action)
        elif action in (Action.SOFT_OFF, Action.FORCE_OFF) and prev in (State.ON, State.STOPPING):
            self._begin(State.STOPPING, action)
        # FORCE_OFF con el PC "apagado" (colgado sin ping): sin transición
        self._mark_change()

    # ---- internos --------------------------------------------------------
    def _begin(self, state: State, action: Action) -> None:
        self._transition = state
        self._transition_started = self._clock()
        self._transition_action = action

    def _resolve_transition(self) -> None:
        if self._transition is State.STARTING and self._detected is State.ON:
            self._transition = None
        elif self._transition is State.STOPPING and self._detected is State.OFF:
            self._transition = None

    def _expire_transition(self) -> None:
        if self._transition and self._clock() - self._transition_started >= self._timeout:
            action = self._transition_action
            self._notice = ("no_effect", action, self._wall())
            self._transition = None
            self.emit("no_effect", action=action.value if action else None)
            self._mark_change()

    def _mark_change(self) -> None:
        if self.state is not self._last_effective:
            old, self._last_effective = self._last_effective, self.state
            self._since = self._wall()
            self.emit("state_change", old=old.value, new=self.state.value)
