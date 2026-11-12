import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.notifier import Notifier, default_post
from tests.conftest import CODE, ORIGIN

URL = "https://ntfy.example/mi-tema-largo"


class Recorder:
    def __init__(self, delay=0.0, fail=False):
        self.calls = []
        self.delay, self.fail = delay, fail

    def __call__(self, server, payload, token):
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise OSError("sin red")
        self.calls.append((server, payload, token))


def make(**kw):
    rec = kw.pop("rec", None) or Recorder()
    return Notifier(URL, kw.pop("token", ""), post=rec, **kw), rec


async def run_all(n, events):
    task = asyncio.create_task(n.run())
    for e in events:
        n.handle(e)
    await n.drain()
    task.cancel()


def ev(type, **data):
    return {"ts": 1_700_000_000.0, "type": type, **data}


async def test_disabled_without_url_never_sends():
    rec = Recorder()
    n = Notifier("", post=rec)
    assert n.enabled is False
    n.handle(ev("login_ok", ip="1.1.1.1"))
    assert n.send("x", "y") is False
    assert rec.calls == []


async def test_expected_events_become_notifications_and_payload_shape():
    n, rec = make(token="tk_abc")
    await run_all(n, [
        ev("action_accepted", action="power_on", source="panel", ip="1.1.1.1"),
        ev("no_effect", action="power_on"),
        ev("login_ok", ip="203.0.113.9"),
        ev("lockout", ip="198.51.100.4", attempts=5),
        ev("scheduled_off_result", result="forced"),
    ])
    titles = [c[1]["title"] for c in rec.calls]
    assert titles == ["Acción enviada", "Sin efecto", "Navegador nuevo autorizado", "Bloqueo por intentos fallidos", "Apagado programado"]
    server, payload, token = rec.calls[2]
    assert server == "https://ntfy.example" and payload["topic"] == "mi-tema-largo" and token == "tk_abc"
    assert "203.0.113.9" in payload["message"]
    assert "198.51.100.4" in rec.calls[3][1]["message"] and "5" in rec.calls[3][1]["message"]
    assert "forzar" in rec.calls[4][1]["message"]


async def test_login_notification_has_time_and_origin():
    n, rec = make(tz="America/Bogota")
    await run_all(n, [ev("login_ok", ip="203.0.113.9")])
    msg = rec.calls[0][1]["message"]
    assert "203.0.113.9" in msg and "14/11" in msg and ":" in msg  # 1_700_000_000 = 14 nov 2023


async def test_irrelevant_events_do_not_notify():
    n, rec = make()
    await run_all(n, [ev("logout"), ev("state_change", old="on", new="off"), ev("schedule_set", kind="on")])
    assert rec.calls == []


async def test_notifications_never_contain_secrets():
    n, rec = make()
    await run_all(n, [ev("login_ok", ip="1.1.1.1", code="123456789", token="tok-secreto", cookie="c"),
                      ev("lockout", ip="1.1.1.1", attempts=5, code="999999999")])
    raw = json.dumps([c[1] for c in rec.calls])
    for secret in ("123456789", "tok-secreto", "999999999", "cookie"):
        assert secret not in raw


async def test_scheduled_off_steps_are_quiet_but_result_is_not():
    n, rec = make()
    await run_all(n, [
        ev("action_accepted", action="soft_off", source="schedule_off"),
        ev("action_accepted", action="force_off", source="schedule_force"),
        ev("scheduled_off_result", result="forced"),
    ])
    assert [c[1]["title"] for c in rec.calls] == ["Apagado programado"]


async def test_no_effect_suppressed_while_off_wait_is_active():
    waiting = {"v": True}
    n, rec = make(suppress_no_effect=lambda: waiting["v"])
    await run_all(n, [ev("no_effect", action="soft_off")])
    assert rec.calls == []
    waiting["v"] = False
    await run_all(n, [ev("no_effect", action="soft_off")])
    assert len(rec.calls) == 1


async def test_failing_destination_does_not_raise_and_consumer_survives(caplog):
    rec = Recorder(fail=True)
    n, _ = make(rec=rec)
    task = asyncio.create_task(n.run())
    n.handle(ev("login_ok", ip="1.1.1.1"))
    await n.drain()
    rec.fail = False
    n.handle(ev("login_ok", ip="2.2.2.2"))
    await n.drain()
    task.cancel()
    assert len(rec.calls) == 1  # el consumidor sigue vivo tras el fallo
    assert any("no se pudo enviar" in r.message for r in caplog.records)


async def test_slow_destination_does_not_block_the_emitter():
    rec = Recorder(delay=0.4)
    n, _ = make(rec=rec)
    task = asyncio.create_task(n.run())
    t0 = time.monotonic()
    for i in range(5):
        n.handle(ev("login_ok", ip=f"1.1.1.{i}"))
    assert time.monotonic() - t0 < 0.1  # encolar es inmediato
    task.cancel()


async def test_hourly_limit_drops_the_21st_and_recovers_after_an_hour():
    now = {"t": 1000.0}
    n, rec = make(clock=lambda: now["t"])
    results = [n.send("t", f"m{i}") for i in range(25)]
    assert results.count(True) == 20 and n.dropped == 5
    now["t"] += 3601
    assert n.send("t", "otra") is True


async def test_sustained_attack_sends_at_most_20_per_hour():
    n, rec = make()
    await run_all(n, [ev("lockout", ip=f"10.0.0.{i % 250}", attempts=5) for i in range(100)])
    assert len(rec.calls) == 20


async def test_full_queue_drops_instead_of_blocking():
    n, _ = make(queue_max=3, max_per_hour=100)
    assert [n.send("t", str(i)) for i in range(5)] == [True, True, True, False, False]


# ---- envío real por HTTP contra un servidor local --------------------------------------
class _Sink(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Sink.received.append((self.path, dict(self.headers), json.loads(body)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


@pytest.fixture
def sink():
    _Sink.received = []
    srv = HTTPServer(("127.0.0.1", 0), _Sink)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def test_default_post_sends_utf8_json_with_bearer_token(sink):
    port = sink.server_address[1]
    default_post(f"http://127.0.0.1:{port}", {"topic": "t", "title": "Acción", "message": "¿Apagar?"}, "tk_1")
    path, headers, body = _Sink.received[0]
    assert headers["Authorization"] == "Bearer tk_1" and headers["Content-Type"] == "application/json"
    assert body["title"] == "Acción" and body["message"] == "¿Apagar?"


def test_default_post_raises_when_unreachable():
    with pytest.raises(OSError):
        default_post("http://127.0.0.1:9", {"topic": "t", "message": "x"}, "", timeout=1)


# ---- integración: el fallo de ntfy no afecta al control ---------------------------------
async def test_action_works_when_ntfy_is_down(tmp_path):
    from tests.conftest import Env

    env = Env(tmp_path)
    bad = Notifier("http://127.0.0.1:9/tema", post=Recorder(fail=True))
    from app.main import create_app

    env.app = create_app(env.cfg, env.relay, env.machine, env.store, env.limiter, None, login_delay_s=0,
                         bus=env.bus, history=env.history, notifier=bad)
    env.set_off()
    task = asyncio.create_task(bad.run())
    async with env.logged_in() as c:
        r = await c.post("/api/action", json={"type": "power_on"}, headers=ORIGIN)
        assert r.status_code == 202
        await asyncio.sleep(0.05)
    assert [e[1] for e in env.driver.events] == ["on", "off"]
    task.cancel()
