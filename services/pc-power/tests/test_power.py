import itertools

import pytest

from app.monitor import Monitor
from app.power import ALLOWED, Action, PowerMachine, State


class Clk:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def adv(self, s):
        self.t += s


def machine(timeout=120.0):
    c = Clk()
    return PowerMachine(transition_timeout_s=timeout, clock=c, wall=c), c


def ping(m, ok, n=1):
    for _ in range(n):
        m.on_ping(ok)


def test_initial_state_is_checking_and_no_actions():
    m, _ = machine()
    assert m.state is State.CHECKING
    assert not any(m.allowed(a) for a in Action)


def test_one_ok_ping_means_on():
    m, _ = machine()
    ping(m, True)
    assert m.state is State.ON


def test_three_failures_means_off_not_before():
    m, _ = machine()
    ping(m, False, 2)
    assert m.state is State.CHECKING  # aún sin estado definitivo
    ping(m, False)
    assert m.state is State.OFF


def test_isolated_loss_keeps_on():
    m, _ = machine()
    ping(m, True)
    ping(m, False)
    assert m.state is State.ON
    ping(m, True)
    ping(m, False, 2)
    assert m.state is State.ON  # el contador se reinició con el ok intermedio


def test_pc_stops_responding_goes_off():
    m, _ = machine()
    ping(m, True)
    ping(m, False, 3)
    assert m.state is State.OFF


# ---- tabla acción x estado -------------------------------------------------
def at_state(state):
    m, c = machine()
    if state is State.CHECKING:
        return m
    if state is State.ON:
        ping(m, True)
    elif state is State.OFF:
        ping(m, False, 3)
    elif state is State.STARTING:
        ping(m, False, 3)
        m.on_action_started(Action.POWER_ON)
    elif state is State.STOPPING:
        ping(m, True)
        m.on_action_started(Action.SOFT_OFF)
    assert m.state is state
    return m


EXPECTED = {
    Action.POWER_ON: {State.OFF},
    Action.SOFT_OFF: {State.ON},
    Action.FORCE_OFF: {State.ON, State.OFF, State.STOPPING},
}


@pytest.mark.parametrize("action,state", list(itertools.product(Action, State)))
def test_action_state_table(action, state):
    m = at_state(state)
    assert m.allowed(action) is (state in EXPECTED[action])
    assert ALLOWED[action] == frozenset(EXPECTED[action])


# ---- transiciones -----------------------------------------------------------
def test_power_on_success_flow():
    m, c = machine()
    ping(m, False, 3)
    m.on_action_started(Action.POWER_ON)
    assert m.state is State.STARTING
    ping(m, False, 5)  # sigue arrancando: no vuelve a off
    c.adv(40)
    assert m.state is State.STARTING
    ping(m, True)
    assert m.state is State.ON
    assert m.snapshot()["notice"] is None


def test_soft_off_success_flow():
    m, c = machine()
    ping(m, True)
    m.on_action_started(Action.SOFT_OFF)
    assert m.state is State.STOPPING
    ping(m, True, 3)  # sigue respondiendo mientras apaga
    assert m.state is State.STOPPING
    ping(m, False, 2)
    assert m.state is State.STOPPING
    ping(m, False)
    assert m.state is State.OFF


def test_force_off_while_on_goes_stopping():
    m, _ = machine()
    ping(m, True)
    m.on_action_started(Action.FORCE_OFF)
    assert m.state is State.STOPPING


def test_force_off_while_off_has_no_transition():
    m, _ = machine()
    ping(m, False, 3)
    m.on_action_started(Action.FORCE_OFF)
    assert m.state is State.OFF


def test_starting_timeout_returns_to_detected_with_notice():
    m, c = machine(timeout=120)
    ping(m, False, 3)
    m.on_action_started(Action.POWER_ON)
    c.adv(119)
    ping(m, False)
    assert m.state is State.STARTING
    c.adv(2)
    ping(m, False)
    assert m.state is State.OFF
    assert m.snapshot()["notice"] == {"code": "no_effect", "action": "power_on"}


def test_stopping_timeout_returns_to_on_with_notice():
    m, c = machine(timeout=60)
    ping(m, True)
    m.on_action_started(Action.SOFT_OFF)
    c.adv(61)
    ping(m, True)
    assert m.state is State.ON
    assert m.snapshot()["notice"]["code"] == "no_effect"


def test_timeout_detected_even_without_pings():
    m, c = machine(timeout=10)
    ping(m, True)
    m.on_action_started(Action.SOFT_OFF)
    c.adv(11)
    assert m.snapshot()["state"] == "on"


def test_notice_expires_and_clears_on_next_action():
    m, c = machine(timeout=10)
    ping(m, False, 3)
    m.on_action_started(Action.POWER_ON)
    c.adv(11)
    assert m.snapshot()["notice"] is not None
    c.adv(31)
    assert m.snapshot()["notice"] is None

    m2, c2 = machine(timeout=10)
    ping(m2, False, 3)
    m2.on_action_started(Action.POWER_ON)
    c2.adv(11)
    assert m2.snapshot()["notice"] is not None
    m2.on_action_started(Action.POWER_ON)
    assert m2.snapshot()["notice"] is None


def test_since_tracks_last_change():
    m, c = machine()
    start = c.t
    ping(m, True)
    assert m.snapshot()["since"] == start
    c.adv(7200)
    ping(m, True)  # sin cambio de estado
    snap = m.snapshot()
    assert snap["since"] == start
    assert snap["now"] - snap["since"] == 7200
    ping(m, False, 3)
    assert m.snapshot()["since"] == c.t


# ---- monitor ----------------------------------------------------------------
async def test_monitor_step_feeds_machine_with_sequence():
    m, _ = machine()
    seq = iter([True, False, False, False])
    calls = []

    async def fake_ping(host):
        calls.append(host)
        return next(seq)

    mon = Monitor("192.168.10.50", 3, m, fake_ping)
    await mon.step()
    assert m.state is State.ON
    await mon.step()
    await mon.step()
    assert m.state is State.ON
    await mon.step()
    assert m.state is State.OFF
    assert calls == ["192.168.10.50"] * 4


async def test_monitor_ping_exception_counts_as_failure():
    m, _ = machine()

    async def broken(host):
        raise OSError("sin ping")

    mon = Monitor("192.168.10.50", 3, m, broken)
    for _ in range(3):
        assert await mon.step() is False
    assert m.state is State.OFF
