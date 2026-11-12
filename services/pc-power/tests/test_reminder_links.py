import asyncio
import re

import httpx

from app.main import create_app
from app.notifier import Notifier
from app.reminder import Reminders
from tests.conftest import Env

H = 3600


class Capture(Notifier):
    """Notificador activo que, en vez de enviar, guarda lo que se publicaría."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.sent = []

    def send(self, title, message, **kw):
        self.sent.append({"title": title, "message": message, **kw})
        return True


class World:
    def __init__(self, tmp_path, cooldown_s=0.0, public_url="https://casa.example"):
        self.env = Env(tmp_path, cooldown_s=cooldown_s,
                       extra_env={"NTFY_URL": "https://ntfy.example/tema-largo", "PUBLIC_URL": public_url})
        self.now = {"t": 1_700_000_000.0}
        self.notifier = Capture(self.env.cfg.ntfy_url)
        self.rem = Reminders(self.env.cfg, self.env.machine, self.notifier, self.env.controller,
                             self.env.bus, tmp_path / "reminders.json", clock=lambda: self.now["t"])
        self.env.app = create_app(
            self.env.cfg, self.env.relay, self.env.machine, self.env.store, self.env.limiter, None,
            login_delay_s=0, bus=self.env.bus, history=self.env.history, controller=self.env.controller,
            scheduler=self.env.scheduler, notifier=self.notifier, reminders=self.rem,
        )

    def new_token(self):
        self.rem._send(self.now["t"], 4 * H)
        url = self.notifier.sent[-1]["actions"][0]["url"]
        return re.search(r"/r/([^/]+)/off", url).group(1)

    @property
    def pulses(self):
        return [e[1] for e in self.env.driver.events].count("on")


# ======================== lógica de los enlaces =====================================
async def test_off_with_pc_on_sends_short_pulse_and_consumes_the_link(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    tok = w.new_token()
    assert w.rem.consume(tok, "off", "203.0.113.4") == 204
    await asyncio.sleep(0.01)
    assert w.pulses == 1 and w.env.durations == [0.5]
    ev = w.env.of("action_accepted")[0]
    assert ev["source"] == "reminder" and ev["action"] == "soft_off" and ev["ip"] == "203.0.113.4"
    assert w.env.of("reminder_off")
    assert w.rem.consume(tok, "off") == 404  # reutilizado
    assert w.rem.consume(tok, "keep") == 404


async def test_off_with_pc_already_off_does_not_pulse(tmp_path):
    w = World(tmp_path)
    w.env.set_off()
    tok = w.new_token()
    assert w.rem.consume(tok, "off") == 204
    await asyncio.sleep(0.01)
    assert w.pulses == 0 and not w.env.of("reminder_off")


async def test_keep_discards_and_disables_the_off_button(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    tok = w.new_token()
    assert w.rem.consume(tok, "keep") == 204
    assert w.env.of("reminder_keep") and w.pulses == 0
    assert w.rem.consume(tok, "off") == 404  # el Apagar de ese recordatorio deja de funcionar
    await asyncio.sleep(0.01)
    assert w.pulses == 0


async def test_invalid_expired_and_unknown_links_are_rejected(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    tok = w.new_token()
    for bad_token in ("inventado", "", "A" * 43, tok[:-1] + ("A" if tok[-1] != "A" else "B")):
        assert w.rem.consume(bad_token, "off") == 404
    for bad_kind in ("force_off", "on", "FORCE", "off/", ""):
        assert w.rem.consume(tok, bad_kind) == 404
    w.now["t"] += 12 * H + 1  # caducó a las 12 h
    assert w.rem.consume(tok, "off") == 404
    await asyncio.sleep(0.01)
    assert w.pulses == 0


async def test_new_reminder_invalidates_the_previous_link(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    old = w.new_token()
    w.now["t"] += 5 * H
    new = w.new_token()
    assert w.rem.consume(old, "off") == 404
    assert w.rem.consume(new, "keep") == 204


async def test_busy_relay_keeps_the_link_alive_for_a_retry(tmp_path):
    w = World(tmp_path, cooldown_s=5.0)
    w.env.set_on()
    tok = w.new_token()
    w.env.controller.request(__import__("app.power", fromlist=["Action"]).Action.FORCE_OFF, "panel")  # relé ocupado
    await asyncio.sleep(0.01)
    assert w.rem.consume(tok, "off") == 409
    w.env.relay._cooldown_until = 0  # termina el enfriamiento
    w.env.machine.on_ping(True)
    w.env.machine._transition = None  # el panel dejó el estado en transición; se normaliza para el reintento
    assert w.rem.consume(tok, "off") == 204  # el mismo enlace sigue valiendo


async def test_only_hashes_are_persisted_and_survive_restart(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    tok = w.new_token()
    raw = (tmp_path / "reminders.json").read_text()
    assert tok not in raw
    again = Reminders(w.env.cfg, w.env.machine, w.notifier, w.env.controller, w.env.bus,
                      tmp_path / "reminders.json", clock=lambda: w.now["t"])
    assert again.consume(tok, "keep") == 204  # el enlace sobrevive a un reinicio


# ======================== HTTP: ruta pública sin sesión ======================================
async def http(w):
    transport = httpx.ASGITransport(app=w.env.app, client=("198.51.100.20", 4444))
    return httpx.AsyncClient(transport=transport, base_url="https://testserver")


def shape(r):
    return r.status_code, r.content, {k: v for k, v in r.headers.items() if k != "date"}


async def test_post_link_works_without_session_and_creates_none(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    tok = w.new_token()
    async with await http(w) as c:
        r = await c.post(f"/r/{tok}/off")  # sin cookies, sin Origin
        assert r.status_code == 204 and "set-cookie" not in r.headers
        await asyncio.sleep(0.01)
        assert w.pulses == 1
        assert (await c.get("/api/status")).status_code == 404  # no hay sesión
        assert (await c.get("/")).text.count('name="code"') == 1  # sigue pidiendo el código


async def test_get_and_wrong_kind_are_404_and_do_not_consume(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    tok = w.new_token()
    async with await http(w) as c:
        assert (await c.get(f"/r/{tok}/off")).status_code == 404
        for kind in ("force_off", "on", "panel"):
            assert (await c.post(f"/r/{tok}/{kind}")).status_code == 404
        assert (await c.post(f"/r/{tok}/keep")).status_code == 204  # el enlace seguía intacto


async def test_all_failures_look_identical(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    used = w.new_token()
    expired = w.new_token()
    async with await http(w) as c:
        await c.post(f"/r/{used}/keep")
        w.now["t"] += 13 * H
        responses = [
            await c.post("/r/inventado/off"),   # inventado
            await c.post(f"/r/{used}/off"),     # usado
            await c.post(f"/r/{expired}/off"),  # caducado
            await c.get("/r/inventado/off"),    # método incorrecto
            await c.post("/r/x/otra"),          # acción desconocida
        ]
    assert len({str(shape(r)) for r in responses}) == 1
    assert responses[0].status_code == 404 and responses[0].content == b""
    assert w.pulses == 0


async def test_link_cannot_reach_other_actions_or_the_panel(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    tok = w.new_token()
    async with await http(w) as c:
        await c.post(f"/r/{tok}/keep")
        for method, path in (("POST", "/api/action"), ("GET", "/api/status"), ("GET", "/static/panel.js"),
                             ("POST", "/api/logout-all"), ("GET", "/api/events")):
            r = await c.request(method, path, headers={"Origin": "https://testserver"})
            assert r.status_code == 404 and r.content == b"", path


async def test_http_double_use_pulses_once(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    tok = w.new_token()
    async with await http(w) as c:
        a, b = await asyncio.gather(c.post(f"/r/{tok}/off"), c.post(f"/r/{tok}/off"))
    assert sorted([a.status_code, b.status_code]) == [204, 404]
    await asyncio.sleep(0.01)
    assert w.pulses == 1


async def test_rate_limit_applies_even_to_valid_links_then_recovers(tmp_path):
    w = World(tmp_path)
    w.env.set_on()
    tok = w.new_token()
    async with await http(w) as c:
        for i in range(10):
            assert (await c.post(f"/r/falso-{i}/off")).status_code == 404
        assert (await c.post(f"/r/{tok}/keep")).status_code == 404  # límite: 10 por minuto
        w.now["t"] += 61
        assert (await c.post(f"/r/{tok}/keep")).status_code == 204  # y se recupera


async def test_route_does_not_exist_without_reminders(tmp_path):
    env = Env(tmp_path)  # sin ntfy ni recordatorios
    async with env.client() as c:
        r = await c.post("/r/cualquiera/off")
        assert r.status_code == 404 and r.content == b""
