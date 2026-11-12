import asyncio

from tests.conftest import CODE, ORIGIN


async def test_login_logout_and_actions_emit_once_each(env):
    env.set_off()  # checking -> off
    async with env.client() as c:
        await c.post("/login", data={"code": CODE}, headers=ORIGIN)
        assert len(env.of("login_ok")) == 1
        await c.post("/api/action", json={"type": "power_on"}, headers=ORIGIN)
        acts = env.of("action_accepted")
        assert len(acts) == 1 and acts[0]["action"] == "power_on" and acts[0]["source"] == "panel"
        assert acts[0]["ip"] == "127.0.0.1"
        await c.post("/api/logout", headers=ORIGIN)
        assert len(env.of("logout")) == 1
        await c.post("/login", data={"code": CODE}, headers=ORIGIN)
        await c.post("/api/logout-all", headers=ORIGIN)
        assert len(env.of("logout_all")) == 1


async def test_rejected_actions_do_not_emit(env):
    env.set_on()
    async with env.logged_in() as c:
        r = await c.post("/api/action", json={"type": "power_on"}, headers=ORIGIN)
        assert r.status_code == 409
    assert env.of("action_accepted") == []


async def test_lockout_event_emitted_once_at_threshold(env):
    async with env.client(forwarded="203.0.113.5") as c:
        for _ in range(8):
            await c.post("/login", data={"code": "mal-codigo-1"}, headers=ORIGIN)
    locks = env.of("lockout")
    assert len(locks) == 1 and locks[0]["ip"] == "203.0.113.5" and locks[0]["attempts"] == 5


async def test_state_change_events(env):
    env.set_off()
    assert [(e["old"], e["new"]) for e in env.of("state_change")] == [("checking", "off")]
    env.machine.on_ping(True)
    assert ("off", "on") in [(e["old"], e["new"]) for e in env.of("state_change")]


async def test_events_endpoint_newest_first_and_requires_session(env):
    async with env.client() as anon:
        r = await anon.get("/api/events")
        assert r.status_code == 404 and r.content == b""
    env.set_off()
    async with env.logged_in() as c:
        await c.post("/api/action", json={"type": "power_on"}, headers=ORIGIN)
        await asyncio.sleep(0.01)
        data = (await c.get("/api/events")).json()
        types = [e["type"] for e in data]
        assert types[0] == "action_accepted" and "login_ok" in types and "state_change" in types
        assert all("text" in e for e in data)
        assert [e["ts"] for e in data] == sorted((e["ts"] for e in data), reverse=True)
        assert len((await c.get("/api/events", params={"limit": 1})).json()) == 1


async def test_history_never_contains_codes_or_tokens(env, tmp_path):
    async with env.client() as c:
        await c.post("/login", data={"code": "codigo-equivocado-9"}, headers=ORIGIN)
        await c.post("/login", data={"code": CODE}, headers=ORIGIN)
        token = c.cookies.get("pcp_session")
    path = tmp_path / "events.jsonl"
    raw = path.read_text() if path.exists() else ""
    assert "codigo-equivocado-9" not in raw and CODE not in raw
    assert not token or token not in raw


async def test_failing_subscriber_does_not_break_the_action(env):
    def boom(e):
        raise RuntimeError("suscriptor roto")

    env.bus.subscribe(boom)
    env.set_off()
    async with env.logged_in() as c:
        r = await c.post("/api/action", json={"type": "power_on"}, headers=ORIGIN)
        assert r.status_code == 202
