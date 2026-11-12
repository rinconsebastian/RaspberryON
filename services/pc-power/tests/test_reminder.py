import json
import re
from datetime import datetime

from app.notifier import Notifier
from app.power import Action
from app.reminder import Reminders, fmt_hours
from tests.test_schedule import BASE, BOGOTA, Rig

H = 3600


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, server, payload, token):
        self.calls.append(payload)


def build(tmp_path, public_url="https://casa.example", ntfy="https://ntfy.example/tema-largo", **env):
    extra = {"NTFY_URL": ntfy, **({"PUBLIC_URL": public_url} if public_url else {}), **env}
    rig = Rig(tmp_path, extra_env={k: v for k, v in extra.items() if v})
    rec = Recorder()
    notifier = Notifier(ntfy, post=rec, clock=rig.clk, tz="America/Bogota", max_per_hour=1000)
    rem = Reminders(rig.cfg, rig.machine, notifier, rig.controller, rig.bus, tmp_path / "reminders.json", clock=rig.clk)
    return rig, rem, notifier, rec


def step(rig, rem, seconds, every=60):
    """Avanza el reloj simulado llamando a tick() cada minuto, como el bucle real."""
    done = 0
    while done < seconds:
        d = min(every, seconds - done)
        rig.clk.t += d
        done += d
        rem.tick()


def sent_times(rig):
    return [datetime.fromtimestamp(e["ts"], BOGOTA).strftime("%H:%M") for e in rig.of("reminder_sent")]


def test_fmt_hours():
    assert fmt_hours(4 * H) == "4 h" and fmt_hours(4 * H + 30 * 60) == "4 h 30 min"


def test_first_reminder_exactly_after_four_hours(tmp_path):
    rig, rem, n, rec = build(tmp_path)
    rig.ping_on()
    step(rig, rem, 4 * H - 60)
    assert not rig.of("reminder_sent")
    step(rig, rem, 60)
    assert sent_times(rig) == ["16:00"]
    assert rig.of("reminder_sent")[0]["hours"] == 4.0


def test_reminder_message_says_how_long_the_pc_has_been_on(tmp_path):
    rig, rem, n, rec = build(tmp_path)
    rig.ping_on()
    step(rig, rem, 4 * H)

    async def go():
        import asyncio
        task = asyncio.create_task(n.run())
        await n.drain()
        task.cancel()

    import asyncio
    asyncio.run(go())
    p = rec.calls[0]
    assert "4 h" in p["message"] and "¿Apagar" in p["title"] and "apagarlo" in p["message"]


def test_counter_restarts_when_the_pc_turned_off_in_between(tmp_path):
    rig, rem, n, rec = build(tmp_path)
    rig.ping_on()
    step(rig, rem, 3 * H)  # a las 3 horas…
    rig.ping_off()  # …se apaga
    step(rig, rem, 30 * 60)
    rig.ping_on()  # y se vuelve a encender
    step(rig, rem, 4 * H - 120)
    assert not rig.of("reminder_sent")
    step(rig, rem, 180)
    assert len(rig.of("reminder_sent")) == 1


def test_repeats_indefinitely_at_9pm_and_6am(tmp_path):
    rig, rem, n, rec = build(tmp_path)
    rig.ping_on()
    step(rig, rem, 44 * H)  # de las 12:00 hasta las 08:00 de dos días después
    assert sent_times(rig) == ["16:00", "21:00", "06:00", "21:00", "06:00"]


def test_no_duplicate_when_first_reminder_is_close_to_a_fixed_time(tmp_path):
    rig, rem, n, rec = build(tmp_path)
    step(rig, rem, 4 * H + 45 * 60)  # 16:45, aún sin estado
    rig.ping_on()
    step(rig, rem, 4 * H)  # primer aviso a las 20:45
    assert sent_times(rig) == ["20:45"]
    step(rig, rem, 20 * 60)  # pasa por las 21:00: hubo un aviso hace < 30 min
    assert sent_times(rig) == ["20:45"]
    step(rig, rem, 10 * H)  # hasta las 07:05
    assert sent_times(rig) == ["20:45", "06:00"]


def test_reminders_stop_when_the_pc_turns_off(tmp_path):
    rig, rem, n, rec = build(tmp_path)
    rig.ping_on()
    step(rig, rem, 4 * H)
    assert len(rig.of("reminder_sent")) == 1
    rig.ping_off()
    step(rig, rem, 30 * H)
    assert len(rig.of("reminder_sent")) == 1  # ni 21:00 ni 06:00
    rig.ping_on()
    step(rig, rem, 3 * H)
    assert len(rig.of("reminder_sent")) == 1  # hay que volver a cumplir las 4 h


async def test_no_reminder_while_the_pc_is_shutting_down(tmp_path):
    rig, rem, n, rec = build(tmp_path)
    rig.ping_on()
    step(rig, rem, 4 * H - 60)
    rig.controller.request(Action.SOFT_OFF, "panel")  # estado "apagando"
    step(rig, rem, 90, every=30)  # cumple las 4 h en transición
    assert not rig.of("reminder_sent")


def test_disabled_notifier_generates_no_reminders(tmp_path):
    rig = Rig(tmp_path)
    off = Notifier("", clock=rig.clk)
    rem = Reminders(rig.cfg, rig.machine, off, rig.controller, rig.bus, tmp_path / "r.json", clock=rig.clk)
    rig.ping_on()
    step(rig, rem, 30 * H)
    assert not rig.of("reminder_sent")


def test_custom_threshold_and_times(tmp_path):
    rig, rem, n, rec = build(tmp_path, REMINDER_AFTER_H="1", REMINDER_TIMES="14:00,23:30")
    rig.ping_on()
    step(rig, rem, 14 * H)
    assert sent_times(rig) == ["13:00", "14:00", "23:30"]  # 13:00 por las horas encendido


# ---- 6.3: contenido publicado (acciones de ntfy) -----------------------------------------------
def payload_after_first_reminder(tmp_path, **kw):
    import asyncio

    rig, rem, n, rec = build(tmp_path, **kw)
    rig.ping_on()
    step(rig, rem, 4 * H)

    async def go():
        task = asyncio.create_task(n.run())
        await n.drain()
        task.cancel()

    asyncio.run(go())
    return rig, rem, rec.calls[0]


def test_published_actions_with_public_url(tmp_path):
    rig, rem, payload = payload_after_first_reminder(tmp_path, public_url="https://casa.example")
    acts = payload["actions"]
    assert [a["label"] for a in acts] == ["Apagar", "Mantener encendido"]
    for a in acts:
        assert a["action"] == "http" and a["method"] == "POST" and a["clear"] is True
    off, keep = acts[0]["url"], acts[1]["url"]
    m = re.fullmatch(r"https://casa\.example/pc/r/([A-Za-z0-9_-]{40,})/off", off)
    assert m and keep == off[:-3] + "keep"
    assert payload["topic"] == "tema-largo"


def test_without_public_url_the_reminder_has_no_direct_buttons(tmp_path):
    rig, rem, payload = payload_after_first_reminder(tmp_path, public_url="")
    assert "actions" not in payload
    assert "apagarlo" in payload["message"]


def test_cookie_path_prefix_is_used_in_links(tmp_path):
    rig, rem, payload = payload_after_first_reminder(tmp_path, COOKIE_PATH="/casa/")
    assert payload["actions"][0]["url"].startswith("https://casa.example/casa/r/")


def test_history_and_state_files_never_contain_the_raw_token(tmp_path):
    rig, rem, payload = payload_after_first_reminder(tmp_path)
    token = re.search(r"/r/([^/]+)/off", payload["actions"][0]["url"]).group(1)
    assert token not in json.dumps(rig.events)
    saved = (tmp_path / "reminders.json").read_text()
    assert token not in saved and "used" in saved  # solo se guarda el hash
    assert rig.of("reminder_sent") and "token" not in rig.of("reminder_sent")[0]
