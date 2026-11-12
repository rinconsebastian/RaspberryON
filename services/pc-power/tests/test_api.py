import asyncio
import re
import time

from tests.conftest import CODE, ORIGIN

GENERIC = "Solicitud recibida."


def shape(r):
    """Todo lo observable de una respuesta salvo la cookie de sesión."""
    headers = {k: v for k, v in r.headers.items() if k not in ("set-cookie", "date")}
    return r.status_code, r.content, headers


# ======================= login: respuesta uniforme ===========================
async def test_login_success_sets_hardened_cookie(make_env):
    env = make_env(cookie_path="/pc/")
    async with env.client() as c:
        r = await c.post("/login", data={"code": CODE}, headers=ORIGIN)
    assert r.status_code == 303 and r.headers["location"] == "./?s=1"
    cookie = r.headers["set-cookie"].lower()
    assert "pcp_session=" in cookie
    for attr in ("httponly", "secure", "samesite=strict", "path=/pc/", f"max-age={30 * 86400}"):
        assert attr in cookie


async def test_wrong_empty_missing_and_correct_look_identical(make_env):
    outcomes = {}
    for label, data in [("ok", {"code": CODE}), ("bad", {"code": "incorrecto-1"}), ("empty", {"code": ""}), ("none", {})]:
        e = make_env()
        async with e.client() as c:
            r = await c.post("/login", data=data, headers=ORIGIN)
            outcomes[label] = (shape(r), "set-cookie" in r.headers)
    assert outcomes["ok"][0] == outcomes["bad"][0] == outcomes["empty"][0] == outcomes["none"][0]
    assert outcomes["ok"][1] is True
    assert not outcomes["bad"][1] and not outcomes["empty"][1] and not outcomes["none"][1]


async def test_blocked_attempts_look_identical_and_correct_code_gives_no_session(env):
    async with env.client() as c:
        first = await c.post("/login", data={"code": "mal-codigo-1"}, headers=ORIGIN)
        for _ in range(4):
            await c.post("/login", data={"code": "mal-codigo-1"}, headers=ORIGIN)
        assert env.limiter.ip_blocked("127.0.0.1")
        blocked_right = await c.post("/login", data={"code": CODE}, headers=ORIGIN)
        assert shape(blocked_right) == shape(first)
        assert "set-cookie" not in blocked_right.headers
        assert (await c.get("/api/status")).status_code == 404  # sin sesión


async def test_login_timing_is_fixed_for_success_and_failure(make_env):
    e = make_env(login_delay_s=0.25)
    async with e.client() as c:
        for code in (CODE, "incorrecto-1", ""):
            t = time.monotonic()
            await c.post("/login", data={"code": code}, headers=ORIGIN)
            assert time.monotonic() - t >= 0.24


async def test_generic_message_only_after_submit_and_no_hints(env):
    async with env.client() as c:
        plain = (await c.get("/")).text
        after = (await c.get("/", params={"s": "1"})).text
    assert GENERIC not in plain and GENERIC in after
    for page in (plain, after):
        low = page.lower()
        for word in ("pc", "encender", "apagar", "relé", "raspberry", "error", "incorrecto", "inválid"):
            assert word not in low, word
        assert 'name="code"' in page


async def test_oversized_body_does_not_break_login(env):
    async with env.client() as c:
        r = await c.post("/login", content=b"code=" + b"a" * 100_000, headers={**ORIGIN, "Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 303 and "set-cookie" not in r.headers


async def test_attempts_are_counted_per_real_client_ip(env):
    async with env.client(forwarded="203.0.113.1") as a, env.client(forwarded="203.0.113.2") as b:
        for _ in range(5):
            await a.post("/login", data={"code": "mal-codigo-1"}, headers=ORIGIN)
        assert env.limiter.ip_blocked("203.0.113.1") and not env.limiter.ip_blocked("203.0.113.2")
        r = await b.post("/login", data={"code": CODE}, headers=ORIGIN)
        assert "set-cookie" in r.headers


async def test_forwarded_header_ignored_from_non_local_peer(env):
    async with env.client(ip="198.51.100.9", forwarded="203.0.113.1") as c:
        await c.post("/login", data={"code": "mal-codigo-1"}, headers=ORIGIN)
    assert env.limiter._by_ip.keys() == {"198.51.100.9"}


async def test_cross_origin_login_is_ignored_silently(env):
    async with env.client() as c:
        ok = await c.post("/login", data={"code": CODE}, headers=ORIGIN)
    async with env.client() as c:
        r = await c.post("/login", data={"code": CODE}, headers={"Origin": "https://evil.example"})
        assert shape(r) == shape(ok)
        assert "set-cookie" not in r.headers
        r2 = await c.post("/login", data={"code": CODE})  # sin Origin ni Sec-Fetch-Site
        assert "set-cookie" not in r2.headers
    assert env.limiter._by_ip == {}  # ni siquiera cuenta como intento


async def test_login_via_sec_fetch_site_same_origin(env):
    async with env.client() as c:
        r = await c.post("/login", data={"code": CODE}, headers={"Sec-Fetch-Site": "same-origin"})
        assert "set-cookie" in r.headers


# ======================= rutas protegidas ====================================
PROTECTED = [("GET", "/api/status"), ("POST", "/api/action"), ("POST", "/api/logout"),
             ("POST", "/api/logout-all"), ("GET", "/static/panel.js"), ("GET", "/api/action")]


async def test_protected_routes_are_404_empty_without_session(env):
    env.set_off()
    async with env.client() as c:
        for method, path in PROTECTED:
            r = await c.request(method, path, headers=ORIGIN, json={"type": "power_on"} if method == "POST" else None)
            assert r.status_code == 404 and r.content == b"", (method, path)
    assert env.driver.events == []  # el relé no se accionó


async def test_unknown_routes_are_404_empty_and_docs_disabled(env):
    async with env.client() as c:
        for path in ("/nada", "/docs", "/openapi.json", "/redoc", "/api"):
            r = await c.get(path)
            assert r.status_code == 404 and r.content == b"", path


async def test_forged_cookie_is_rejected(env):
    async with env.client() as c:
        c.cookies.set("pcp_session", "inventada", domain="testserver")
        assert (await c.get("/api/status")).status_code == 404


async def test_security_headers_everywhere_and_no_server_header(env):
    async with env.logged_in() as c:
        for path in ("/", "/api/status", "/nada", "/static/app.css"):
            r = await c.get(path)
            assert "default-src 'self'" in r.headers["content-security-policy"]
            assert r.headers["x-frame-options"] == "DENY"
            assert r.headers["referrer-policy"] == "same-origin"
            assert r.headers["cache-control"] == "no-store"
            assert r.headers["x-robots-tag"] == "noindex"
            assert "server" not in r.headers


async def test_post_from_other_origin_is_rejected_with_session(env):
    env.set_off()
    async with env.logged_in() as c:
        for path, body in (("/api/action", {"type": "power_on"}), ("/api/logout", None), ("/api/logout-all", None)):
            r = await c.post(path, json=body, headers={"Origin": "https://evil.example"})
            assert r.status_code == 403, path
        r = await c.post("/api/action", json={"type": "power_on"})  # sin Origin
        assert r.status_code == 403
        assert env.driver.events == []
        assert (await c.get("/api/status")).status_code == 200  # la sesión sigue viva
        ok = await c.post("/api/action", json={"type": "power_on"}, headers={"Sec-Fetch-Site": "same-origin"})
        assert ok.status_code == 202


# ======================= flujo de la API =====================================
async def test_status_payload_and_panel(env):
    env.set_on()
    async with env.logged_in() as c:
        s = (await c.get("/api/status")).json()
        assert s["state"] == "on" and s["busy"] is False and s["name"] == "Mi PC"
        assert {"since", "now", "notice"} <= s.keys()
        page = await c.get("/")
        assert "Mi PC" in page.text and "static/panel.js" in page.text
        assert "<script>" not in page.text  # la CSP no permite scripts en línea
        assert (await c.get("/static/panel.js")).status_code == 200


async def test_power_on_flow_and_pulse_durations(env):
    env.set_off()
    async with env.logged_in() as c:
        r = await c.post("/api/action", json={"type": "power_on"}, headers=ORIGIN)
        assert r.status_code == 202 and r.json() == {"ok": True, "pulse_ms": 500}
        await asyncio.sleep(0.01)
        assert env.durations == [0.5]
        assert [e[1] for e in env.driver.events] == ["on", "off"]
        s = (await c.get("/api/status")).json()
        assert s["state"] == "starting"
        env.machine.on_ping(True)
        assert (await c.get("/api/status")).json()["state"] == "on"


async def test_short_for_soft_off_and_long_for_force_off(make_env):
    for action, expected in (("soft_off", 0.5), ("force_off", 6.0)):
        e = make_env()
        e.set_on()
        async with e.logged_in() as c:
            r = await c.post("/api/action", json={"type": action}, headers=ORIGIN)
            assert r.status_code == 202
            await asyncio.sleep(0.01)
            assert e.durations == [expected]
            assert e.machine.state.value == "stopping"


async def test_force_off_allowed_when_pc_does_not_answer_ping(env):
    env.set_off()
    async with env.logged_in() as c:
        r = await c.post("/api/action", json={"type": "force_off"}, headers=ORIGIN)
        assert r.status_code == 202
        await asyncio.sleep(0.01)
        assert env.durations == [6.0]


async def test_stale_panel_cannot_trigger_opposite_action(env):
    env.set_on()  # el panel creía "apagado" y mostraba Encender
    async with env.logged_in() as c:
        r = await c.post("/api/action", json={"type": "power_on"}, headers=ORIGIN)
        assert r.status_code == 409 and r.json()["reason"] == "invalid_state"
        env2 = r.json()
        assert env2["state"] == "on"
    env.set_off()
    async with env.logged_in() as c:
        r = await c.post("/api/action", json={"type": "soft_off"}, headers=ORIGIN)
        assert r.status_code == 409
    assert env.driver.events == []


async def test_no_actions_while_checking_or_starting(env):
    async with env.logged_in() as c:
        for a in ("power_on", "soft_off", "force_off"):
            assert (await c.post("/api/action", json={"type": a}, headers=ORIGIN)).status_code == 409
    assert env.driver.events == []


async def test_double_tap_pulses_once(make_env):
    e = make_env(cooldown_s=5.0)
    e.set_off()
    async with e.logged_in() as c:
        a = await c.post("/api/action", json={"type": "power_on"}, headers=ORIGIN)
        b = await c.post("/api/action", json={"type": "power_on"}, headers=ORIGIN)
        assert a.status_code == 202 and b.status_code == 409
        await asyncio.sleep(0.01)
    assert [x[1] for x in e.driver.events] == ["on", "off"]


async def test_two_browsers_at_once_only_first_executes(make_env):
    e = make_env(cooldown_s=5.0, block_pulse=True)
    e.set_on()
    async with e.logged_in() as a, e.logged_in() as b:
        ra, rb = await asyncio.gather(
            a.post("/api/action", json={"type": "force_off"}, headers=ORIGIN),
            b.post("/api/action", json={"type": "force_off"}, headers=ORIGIN),
        )
        assert sorted([ra.status_code, rb.status_code]) == [202, 409]
        loser = ra if ra.status_code == 409 else rb
        assert loser.json()["reason"] == "busy"
        assert (await a.get("/api/status")).json()["busy"] is True
        e.gate.set()
        await asyncio.sleep(0.01)
    assert [x[1] for x in e.driver.events] == ["on", "off"]


async def test_bad_action_payloads_are_400(env):
    env.set_off()
    async with env.logged_in() as c:
        for content in (b"no-json", b'{"type":"explotar"}', b'{"type":5}', b"[]", b""):
            r = await c.post("/api/action", content=content, headers={**ORIGIN, "Content-Type": "application/json"})
            assert r.status_code == 400, content
    assert env.driver.events == []


async def test_logout_revokes_only_this_browser(env):
    async with env.logged_in() as a, env.logged_in() as b:
        r = await a.post("/api/logout", headers=ORIGIN)
        assert r.status_code == 204
        assert (await a.get("/api/status")).status_code == 404
        assert (await a.get("/")).text.count('name="code"') == 1  # vuelve el formulario
        assert (await b.get("/api/status")).status_code == 200


async def test_logout_all_revokes_every_browser_including_current(env):
    async with env.logged_in() as a, env.logged_in() as b:
        assert (await a.post("/api/logout-all", headers=ORIGIN)).status_code == 204
        assert (await a.get("/api/status")).status_code == 404
        assert (await b.get("/api/status")).status_code == 404


async def test_notice_after_transition_timeout(make_env):
    e = make_env()
    e.machine = type(e.machine)(transition_timeout_s=0.01)
    e.app = None
    from app.main import create_app

    e.app = create_app(e.cfg, e.relay, e.machine, e.store, e.limiter, None, login_delay_s=0)
    e.set_off()
    async with e.logged_in() as c:
        await c.post("/api/action", json={"type": "power_on"}, headers=ORIGIN)
        await asyncio.sleep(0.05)
        s = (await c.get("/api/status")).json()
        assert s["state"] == "off" and s["notice"] == {"code": "no_effect", "action": "power_on"}


async def test_sec_fetch_site_takes_precedence_over_origin(env):
    env.set_off()
    async with env.logged_in() as c:
        # Chrome con política estricta envía Origin: null en formularios del propio sitio
        r = await c.post("/api/action", json={"type": "power_on"}, headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"})
        assert r.status_code == 202
        await asyncio.sleep(0.01)
    env2_events = len(env.driver.events)
    async with env.logged_in() as c:
        # Origin "correcto" pero el navegador declara petición entre sitios: se rechaza
        for site in ("cross-site", "same-site", "none"):
            r = await c.post("/api/logout-all", headers={**ORIGIN, "Sec-Fetch-Site": site})
            assert r.status_code == 403, site
        assert (await c.get("/api/status")).status_code == 200
    assert len(env.driver.events) == env2_events


async def test_login_form_post_with_origin_null_and_same_origin_fetch_site(env):
    async with env.client() as c:
        r = await c.post("/login", data={"code": CODE}, headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"})
        assert "set-cookie" in r.headers
    async with env.client() as c:
        r = await c.post("/login", data={"code": CODE}, headers={"Origin": "null", "Sec-Fetch-Site": "cross-site"})
        assert "set-cookie" not in r.headers
