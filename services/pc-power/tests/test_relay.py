import asyncio

import pytest

from app.relay import MockDriver, Relay, RelayBusy


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    async def sleep(self, s):
        self.t += s


def make(cooldown=5.0):
    clock = FakeClock()
    drv = MockDriver(clock)
    return Relay(drv, cooldown_s=cooldown, clock=clock, sleep=clock.sleep), drv, clock


async def test_starts_open():
    _, drv, _ = make()
    assert drv.energized is False
    assert drv.events == []


async def test_pulse_duration_and_open_after():
    relay, drv, clock = make()
    await relay.pulse(0.5)
    assert [e[1] for e in drv.events] == ["on", "off"]
    assert drv.events[1][0] - drv.events[0][0] == pytest.approx(0.5)
    assert drv.energized is False


async def test_long_pulse_duration():
    relay, drv, _ = make()
    await relay.pulse(6.0)
    assert drv.events[1][0] - drv.events[0][0] == pytest.approx(6.0)


async def test_rejects_concurrent_pulse():
    drv = MockDriver()
    gate = asyncio.Event()

    async def slow_sleep(_):
        await gate.wait()

    relay = Relay(drv, cooldown_s=0, sleep=slow_sleep)
    first = asyncio.create_task(relay.pulse(1))
    await asyncio.sleep(0.01)
    assert relay.active and drv.energized
    with pytest.raises(RelayBusy):
        await relay.pulse(1)
    gate.set()
    await first
    assert [e[1] for e in drv.events] == ["on", "off"]  # el rechazado no accionó nada


async def test_double_tap_only_one_pulse():
    drv = MockDriver()
    relay = Relay(drv, cooldown_s=5.0)
    results = await asyncio.gather(relay.pulse(0.01), relay.pulse(0.01), return_exceptions=True)
    assert sum(isinstance(r, RelayBusy) for r in results) == 1
    assert [e[1] for e in drv.events] == ["on", "off"]


async def test_cooldown_rejects_then_allows():
    relay, drv, clock = make(cooldown=5.0)
    await relay.pulse(0.5)
    assert relay.busy and 4.9 < relay.retry_after() <= 5.0
    with pytest.raises(RelayBusy):
        await relay.pulse(0.5)
    clock.t += 4.9
    with pytest.raises(RelayBusy):
        await relay.pulse(0.5)
    clock.t += 0.2
    assert not relay.busy
    await relay.pulse(0.5)
    assert [e[1] for e in drv.events] == ["on", "off", "on", "off"]


async def test_opens_if_sleep_raises():
    drv = MockDriver()

    async def boom(_):
        raise RuntimeError("fallo")

    relay = Relay(drv, sleep=boom)
    with pytest.raises(RuntimeError):
        await relay.pulse(1)
    assert drv.energized is False
    assert [e[1] for e in drv.events] == ["on", "off"]
    assert not relay.active


async def test_opens_if_cancelled_mid_pulse():
    drv = MockDriver()
    relay = Relay(drv, cooldown_s=0)
    task = asyncio.create_task(relay.pulse(60))
    await asyncio.sleep(0.01)
    assert drv.energized
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert drv.energized is False
    assert not relay.active


async def test_opens_if_driver_on_fails():
    class BadDriver(MockDriver):
        def on(self):
            super().on()
            raise OSError("gpio")

    drv = BadDriver()
    relay = Relay(drv)
    with pytest.raises(OSError):
        await relay.pulse(1)
    assert drv.energized is False


async def test_close_leaves_open():
    relay, drv, _ = make()
    relay.close()
    assert drv.energized is False


async def test_start_is_synchronous_and_atomic():
    drv = MockDriver()
    relay = Relay(drv, cooldown_s=5.0)
    t1 = relay.start(0.01)  # sin await: ya está reservado
    with pytest.raises(RelayBusy):
        relay.start(0.01)
    await t1
    assert [e[1] for e in drv.events] == ["on", "off"]


async def test_cancel_before_start_releases_reservation():
    drv = MockDriver()
    relay = Relay(drv, cooldown_s=0)
    t = relay.start(1)
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t
    assert not relay.active
    assert drv.events == []  # nunca llegó a cerrar el relé
