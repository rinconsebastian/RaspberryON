import asyncio

from app.notifier import Notifier
from tests.test_schedule import Rig


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, server, payload, token):
        self.calls.append(payload)


def attach(rig):
    rec = Recorder()
    n = Notifier("https://ntfy.example/tema-largo", post=rec, clock=rig.clk, suppress_no_effect=lambda: rig.sch.quiet)
    rig.bus.subscribe(n.handle)
    return n, rec


async def flush(n):
    task = asyncio.create_task(n.run())
    await n.drain()
    task.cancel()


def titles(rec):
    return [c["title"] for c in rec.calls]


async def test_forced_shutdown_produces_a_single_notification_at_the_end(tmp_path):
    r = Rig(tmp_path)
    n, rec = attach(r)
    r.ping_on()
    r.sch.set("off", "13:00")
    await r.advance(3601)  # pulso corto
    await r.advance(130)  # supera los 120 s de transición de la máquina
    r.machine.on_ping(True)  # la máquina vence su transición y emitiría "sin efecto"
    assert r.of("no_effect")  # el evento existe (queda en el historial)…
    await r.advance(11 * 60)  # …y vence la espera de forzado
    r.ping_off()
    await flush(n)
    assert titles(rec) == ["Apagado programado"]  # …pero solo llega un aviso, con el resultado
    assert "forzar" in rec.calls[0]["message"]


async def test_normal_shutdown_produces_a_single_notification(tmp_path):
    r = Rig(tmp_path)
    n, rec = attach(r)
    r.ping_on()
    r.sch.set("off", "13:00")
    await r.advance(3601)
    await r.advance(7 * 60)
    r.ping_off()
    await flush(n)
    assert titles(rec) == ["Apagado programado"]
    assert "normalidad" in rec.calls[0]["message"]


async def test_failed_shutdown_reports_failed_once_without_extra_no_effect(tmp_path):
    r = Rig(tmp_path)
    n, rec = attach(r)
    r.ping_on()
    r.sch.set("off", "13:00")
    await r.advance(3601)
    await r.advance(11 * 60)  # se fuerza
    await r.advance(125)  # vence el plazo posterior al forzado
    r.machine.on_ping(True)  # la máquina también vence su transición (sin efecto) en este instante
    await flush(n)
    assert titles(rec) == ["Apagado programado"]
    assert "sigue encendido" in rec.calls[0]["message"]


async def test_ordinary_no_effect_still_notifies_when_no_schedule_is_involved(tmp_path):
    r = Rig(tmp_path)
    n, rec = attach(r)
    r.ping_off()
    r.controller.request(__import__("app.power", fromlist=["Action"]).Action.POWER_ON, "panel", "1.1.1.1")
    await r.advance(0, tick=False)
    await r.advance(130, tick=False)
    r.machine.on_ping(False)  # vence la transición: el PC no encendió
    await flush(n)
    assert "Sin efecto" in titles(rec)


async def test_scheduled_steps_do_not_notify_individually(tmp_path):
    r = Rig(tmp_path)
    n, rec = attach(r)
    r.ping_on()
    r.sch.set("off", "13:00")
    await r.advance(3601)
    await r.advance(11 * 60)  # soft_off (schedule_off) y force_off (schedule_force)
    await flush(n)
    assert rec.calls == []  # ni el pulso corto ni el largo avisan por separado
