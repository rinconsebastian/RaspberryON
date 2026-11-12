import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import load_config
from app.control import PowerController
from app.events import EventBus
from app.power import PowerMachine, State
from app.relay import MockDriver, Relay
from app.schedule import ScheduleError, Scheduler, next_occurrence

BOGOTA = ZoneInfo("America/Bogota")
BASE = datetime(2026, 11, 12, 12, 0, 0, tzinfo=BOGOTA).timestamp()  # 12:00 hora de Bogotá


class Clk:
    def __init__(self, t=BASE):
        self.t = t

    def __call__(self):
        return self.t


class Rig:
    def __init__(self, tmp_path, clk=None, force_min=10, cooldown=5.0, keep_state=None, extra_env=None):
        self.clk = clk or Clk()
        self.tmp = tmp_path
        self.cfg = load_config({
            "ACCESS_CODE": "codigo-largo-123", "PC_HOST": "192.168.10.50", "RELAY_ACTIVE_HIGH": "false",
            "RELAY_DRIVER": "mock", "STATE_DIR": str(tmp_path), "TZ": "America/Bogota",
            "OFF_FORCE_AFTER_MIN": str(force_min), **(extra_env or {}),
        })
        self.durations = []
        self.driver = MockDriver(self.clk)

        async def fast_sleep(s):
            self.durations.append(s)
            await asyncio.sleep(0)

        self.relay = Relay(self.driver, cooldown_s=cooldown, clock=self.clk, sleep=fast_sleep)
        self.machine = keep_state or PowerMachine(transition_timeout_s=120, clock=self.clk, wall=self.clk)
        self.bus = EventBus(clock=self.clk)
        self.events = []
        self.bus.subscribe(self.events.append)
        self.machine.emit = self.bus.emit
        self.controller = PowerController(self.cfg, self.relay, self.machine, self.bus)
        self.sch = Scheduler(self.cfg, self.machine, self.controller, self.bus, tmp_path / "schedule.json", clock=self.clk)

    def restart(self, at=None):
        """Nuevo programador sobre los mismos archivos (reinicio del servicio)."""
        if at is not None:
            self.clk.t = at
        self.events.clear()
        self.sch = Scheduler(self.cfg, self.machine, self.controller, self.bus, self.tmp / "schedule.json", clock=self.clk)

    def ping_on(self):
        self.machine.on_ping(True)

    def ping_off(self):
        for _ in range(3):
            self.machine.on_ping(False)

    def of(self, type, **match):
        return [e for e in self.events if e["type"] == type and all(e.get(k) == v for k, v in match.items())]

    def pulses(self):
        return [e[1] for e in self.driver.events].count("on")

    async def advance(self, seconds, tick=True):
        self.clk.t += seconds
        if tick:
            self.sch.tick()
        for _ in range(4):
            await asyncio.sleep(0)


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


# ======================== next_occurrence / zona horaria ==============================
def test_next_occurrence_is_in_configured_timezone():
    at = next_occurrence("07:30", BASE, BOGOTA)  # son las 12:00: la próxima 07:30 es mañana
    assert datetime.fromtimestamp(at, BOGOTA).strftime("%Y-%m-%d %H:%M") == "2026-11-13 07:30"
    assert 0 < at - BASE <= 24 * 3600


def test_next_occurrence_later_today_and_just_passed():
    assert datetime.fromtimestamp(next_occurrence("18:45", BASE, BOGOTA), BOGOTA).day == 12
    assert next_occurrence("12:00", BASE, BOGOTA) - BASE == pytest.approx(24 * 3600, abs=1)


@pytest.mark.parametrize("bad", ["25:00", "12:60", "abc", "", "7:5", "12-30", None, 730])
def test_invalid_times_are_rejected(bad):
    with pytest.raises(ScheduleError) as e:
        next_occurrence(bad, BASE, BOGOTA)
    assert e.value.code == "invalid_time"


def test_single_digit_hour_is_accepted():
    assert datetime.fromtimestamp(next_occurrence("7:30", BASE, BOGOTA), BOGOTA).strftime("%H:%M") == "07:30"


# ======================== encendido programado ========================================
async def test_set_on_when_off_shows_label_and_emits(rig):
    rig.ping_off()
    st = rig.sch.set("on", "07:30")
    assert st["on"] == "07:30" and st["off"] is None and st["tz"] == "America/Bogota"
    assert rig.of("schedule_set", kind="on")


async def test_set_on_requires_pc_off(rig):
    rig.ping_on()
    with pytest.raises(ScheduleError) as e:
        rig.sch.set("on", "07:30")
    assert e.value.code == "invalid_state"
    fresh = Rig(rig.tmp / "otro")
    with pytest.raises(ScheduleError):  # estado "comprobando"
        fresh.sch.set("on", "07:30")


async def test_new_on_schedule_replaces_previous(rig):
    rig.ping_off()
    rig.sch.set("on", "07:30")
    assert rig.sch.set("on", "08:15")["on"] == "08:15"


async def test_on_fires_a_short_pulse_when_pc_is_off(rig):
    rig.ping_off()
    rig.sch.set("on", "13:00")
    await rig.advance(3599)
    assert rig.pulses() == 0
    await rig.advance(2)
    assert rig.pulses() == 1 and rig.durations == [0.5]
    assert rig.sch.on_at is None and rig.of("schedule_fired", kind="on")
    assert rig.of("action_accepted", action="power_on", source="schedule")


async def test_on_is_discarded_without_pulse_when_pc_already_on(rig):
    rig.ping_off()
    rig.sch.set("on", "13:00")
    rig.ping_on()
    await rig.advance(3601)
    assert rig.pulses() == 0 and rig.sch.on_at is None and rig.of("schedule_discarded", kind="on")


async def test_cancel_prevents_the_pulse(rig):
    rig.ping_off()
    rig.sch.set("on", "13:00")
    assert rig.sch.cancel("on") is True
    assert rig.sch.status()["on"] is None and rig.of("schedule_cancelled", kind="on")
    await rig.advance(7200)
    assert rig.pulses() == 0
    n = len(rig.events)
    assert rig.sch.cancel("on") is False and len(rig.events) == n  # nada que cancelar: sin evento


async def test_schedule_survives_restart_and_fires_on_time(rig):
    rig.ping_off()
    rig.sch.set("on", "13:00")
    rig.restart(at=BASE + 600)  # reinicio una hora antes de la hora programada
    assert rig.sch.status()["on"] == "13:00"
    await rig.advance(3000)
    assert rig.pulses() == 1


async def test_overdue_by_two_hours_after_restart_is_discarded(rig):
    rig.ping_off()
    rig.sch.set("on", "13:00")
    rig.restart(at=BASE + 3600 + 2 * 3600)
    assert rig.sch.on_at is None and rig.of("schedule_discarded", kind="on")
    await rig.advance(5)
    assert rig.pulses() == 0


async def test_overdue_by_less_than_five_minutes_after_restart_still_fires(rig):
    rig.ping_off()
    rig.sch.set("on", "13:00")
    rig.restart(at=BASE + 3600 + 240)
    await rig.advance(1)
    assert rig.pulses() == 1


async def test_waits_while_state_is_unknown_then_fires(tmp_path):
    r = Rig(tmp_path)
    r.ping_off()
    r.sch.set("on", "13:00")
    r.restart(at=BASE + 3600 + 10)
    r.machine = PowerMachine(transition_timeout_s=120, clock=r.clk, wall=r.clk)  # reinicio: estado "comprobando"
    r.controller = PowerController(r.cfg, r.relay, r.machine, r.bus)
    r.machine.emit = r.bus.emit
    r.sch = Scheduler(r.cfg, r.machine, r.controller, r.bus, r.tmp / "schedule.json", clock=r.clk)
    await r.advance(5)
    assert r.pulses() == 0 and r.sch.on_at is not None  # espera a conocer el estado
    r.ping_off()
    await r.advance(1)
    assert r.pulses() == 1


async def test_unknown_state_beyond_five_minutes_discards(tmp_path):
    r = Rig(tmp_path)
    r.machine = PowerMachine(transition_timeout_s=120, clock=r.clk, wall=r.clk)
    r.controller = PowerController(r.cfg, r.relay, r.machine, r.bus)
    r.sch = Scheduler(r.cfg, r.machine, r.controller, r.bus, r.tmp / "schedule.json", clock=r.clk)
    r.sch.on_at = r.clk.t + 10
    await r.advance(10 + 301)
    assert r.pulses() == 0 and r.sch.on_at is None


async def test_busy_relay_retries_once_then_discards(tmp_path):
    r = Rig(tmp_path, cooldown=30.0)
    r.ping_off()
    r.sch.set("on", "13:00")
    r.clk.t = BASE + 3600 - 2
    r.relay._cooldown_until = r.clk.t + 8  # relé en enfriamiento a la hora programada
    await r.advance(3)
    assert r.pulses() == 0 and r.sch.on_at is not None  # ocupado: reintento programado
    await r.advance(10)
    assert r.pulses() == 1  # el reintento a los 10 s acciona


async def test_busy_relay_second_attempt_also_busy_discards(tmp_path):
    r = Rig(tmp_path, cooldown=60.0)
    r.ping_off()
    r.sch.set("on", "13:00")
    r.clk.t = BASE + 3600 - 1
    r.relay._cooldown_until = r.clk.t + 100
    await r.advance(2)
    await r.advance(11)
    assert r.pulses() == 0 and r.sch.on_at is None and r.of("schedule_discarded", kind="on")


# ======================== apagado programado ==========================================
async def test_set_off_only_when_pc_on(rig):
    rig.ping_off()
    with pytest.raises(ScheduleError) as e:
        rig.sch.set("off", "23:00")
    assert e.value.code == "invalid_state"
    rig.ping_on()
    assert rig.sch.set("off", "23:00")["off"] == "23:00"
    assert rig.of("schedule_set", kind="off")


async def test_on_and_off_schedules_coexist(rig):
    rig.ping_off()
    rig.sch.set("on", "07:30")
    rig.ping_on()
    st = rig.sch.set("off", "23:00")
    assert st["on"] == "07:30" and st["off"] == "23:00"


async def test_off_fires_soft_pulse_and_opens_wait(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    assert rig.pulses() == 1 and rig.durations == [0.5]
    assert rig.of("action_accepted", action="soft_off", source="schedule_off")
    assert rig.sch.waiting and rig.of("schedule_fired", kind="off")
    assert rig.sch.status()["off_wait"]["force_label"] == "13:10"


async def test_off_discarded_when_pc_already_off(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    rig.ping_off()
    await rig.advance(3601)
    assert rig.pulses() == 0 and rig.sch.off_at is None and rig.of("schedule_discarded", kind="off")


async def test_windows_takes_seven_minutes_to_shut_down_no_force(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    await rig.advance(7 * 60)
    rig.ping_off()  # el PC dejó de responder
    assert not rig.sch.waiting
    assert rig.of("scheduled_off_result", result="normal")
    await rig.advance(20 * 60)
    assert rig.pulses() == 1 and rig.durations == [0.5]  # nunca se envió el pulso largo


async def test_pc_stays_on_after_ten_minutes_gets_forced_then_result_forced(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    await rig.advance(9 * 60)
    assert rig.pulses() == 1  # aún dentro de los 10 minutos
    await rig.advance(2 * 60)
    assert rig.pulses() == 2 and rig.durations == [0.5, 6.0]
    assert rig.of("action_accepted", action="force_off", source="schedule_force")
    assert rig.sch.waiting and not rig.of("scheduled_off_result")
    rig.ping_off()
    assert rig.of("scheduled_off_result", result="forced") and not rig.sch.waiting


async def test_forced_but_pc_still_on_reports_failed(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    await rig.advance(11 * 60)
    assert rig.durations == [0.5, 6.0]
    await rig.advance(119)
    assert rig.sch.waiting
    await rig.advance(3)
    assert rig.of("scheduled_off_result", result="failed") and not rig.sch.waiting


async def test_turned_off_then_on_again_does_not_force(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    await rig.advance(4 * 60)
    rig.ping_off()  # se apagó…
    await rig.advance(60)
    rig.ping_on()  # …y se volvió a encender (a mano o por la propia Raspberry)
    await rig.advance(30 * 60)
    assert rig.pulses() == 1
    assert len(rig.of("scheduled_off_result")) == 1


async def test_user_action_during_wait_cancels_forcing(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    await rig.advance(30)  # fuera del enfriamiento
    rig.bus.emit("action_accepted", action="soft_off", source="panel", ip="1.1.1.1")
    assert not rig.sch.waiting and rig.of("schedule_cancelled", kind="off")
    await rig.advance(20 * 60)
    assert rig.pulses() == 1 and not rig.of("scheduled_off_result")


async def test_reminder_action_also_cancels_wait(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    rig.bus.emit("action_accepted", action="soft_off", source="reminder")
    assert not rig.sch.waiting


async def test_own_pulses_do_not_cancel_the_wait(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    assert rig.sch.waiting  # el soft_off propio (source schedule_off) no se autocancela


async def test_cancel_off_during_wait_stops_forcing(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    assert rig.sch.cancel("off") is True
    await rig.advance(20 * 60)
    assert rig.pulses() == 1 and rig.sch.status()["off_wait"] is None


async def test_wait_survives_restart_and_forces_at_deadline(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    saved = json.loads((rig.tmp / "schedule.json").read_text())
    assert saved["off_wait"]["phase"] == "soft"
    rig.restart(at=rig.clk.t + 60)
    assert rig.sch.waiting
    await rig.advance(11 * 60)
    assert rig.durations == [0.5, 6.0]


async def test_stale_wait_is_discarded_on_restart(rig):
    rig.ping_on()
    rig.sch.set("off", "13:00")
    await rig.advance(3601)
    rig.restart(at=rig.clk.t + 10 * 60 + 400)
    assert not rig.sch.waiting and rig.of("schedule_discarded", kind="off")
    await rig.advance(10)
    assert rig.durations == [0.5]


async def test_force_with_busy_relay_retries_once(tmp_path):
    r = Rig(tmp_path, cooldown=5.0)
    r.ping_on()
    r.sch.set("off", "13:00")
    await r.advance(3601)
    r.clk.t += 600 - 3 - 1
    await r.advance(0, tick=False)
    r.relay._cooldown_until = r.clk.t + 8  # ocupado justo al vencer la espera
    await r.advance(5)
    assert r.pulses() == 1  # reintento pendiente
    await r.advance(11)
    assert r.durations == [0.5, 6.0]


async def test_corrupt_schedule_file_starts_empty(tmp_path):
    (tmp_path / "schedule.json").write_text("{no es json")
    r = Rig(tmp_path)
    assert r.sch.status()["on"] is None and r.sch.status()["off"] is None


async def test_invalid_kind(rig):
    with pytest.raises(ScheduleError):
        rig.sch.set("otro", "12:00")
    with pytest.raises(ScheduleError):
        rig.sch.cancel("otro")
