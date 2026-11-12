from tests.conftest import ORIGIN

JSON = {"Content-Type": "application/json"}


async def test_schedule_routes_require_a_session(env):
    env.set_off()
    async with env.client() as c:
        for method, path in (("GET", "/api/schedule"), ("PUT", "/api/schedule/on"), ("DELETE", "/api/schedule/on"),
                             ("PUT", "/api/schedule/off"), ("DELETE", "/api/schedule/off")):
            r = await c.request(method, path, headers=ORIGIN, content=b'{"time":"07:30"}')
            assert r.status_code == 404 and r.content == b"", (method, path)
    assert env.scheduler.on_at is None


async def test_unknown_kind_is_404(env):
    async with env.logged_in() as c:
        assert (await c.put("/api/schedule/otro", headers={**ORIGIN, **JSON}, content=b'{"time":"07:30"}')).status_code == 404
        assert (await c.delete("/api/schedule/otro", headers=ORIGIN)).status_code == 404


async def test_cross_origin_is_rejected(env):
    env.set_off()
    async with env.logged_in() as c:
        evil = {"Origin": "https://evil.example", **JSON}
        assert (await c.put("/api/schedule/on", headers=evil, content=b'{"time":"07:30"}')).status_code == 403
        assert (await c.delete("/api/schedule/on", headers={"Origin": "https://evil.example"})).status_code == 403
        assert (await c.put("/api/schedule/on", headers=JSON, content=b'{"time":"07:30"}')).status_code == 403  # sin Origin
    assert env.scheduler.on_at is None


async def test_schedule_on_when_off_and_status_shows_it(env):
    env.set_off()
    async with env.logged_in() as c:
        r = await c.put("/api/schedule/on", headers={**ORIGIN, **JSON}, content=b'{"time":"07:30"}')
        assert r.status_code == 200 and r.json()["on"] == "07:30" and r.json()["tz"] == "America/Bogota"
        assert (await c.get("/api/schedule")).json()["on"] == "07:30"
        st = (await c.get("/api/status")).json()
        assert st["schedule"]["on"] == "07:30" and "now" in st["schedule"]
    assert env.of("schedule_set")[0]["kind"] == "on"


async def test_schedule_on_rejected_when_pc_is_on_or_unknown(env):
    async with env.logged_in() as c:  # estado "comprobando"
        r = await c.put("/api/schedule/on", headers={**ORIGIN, **JSON}, content=b'{"time":"07:30"}')
        assert r.status_code == 409 and r.json()["reason"] == "invalid_state"
        env.set_on()
        r = await c.put("/api/schedule/on", headers={**ORIGIN, **JSON}, content=b'{"time":"07:30"}')
        assert r.status_code == 409


async def test_schedule_off_only_when_pc_is_on(env):
    env.set_off()
    async with env.logged_in() as c:
        r = await c.put("/api/schedule/off", headers={**ORIGIN, **JSON}, content=b'{"time":"23:00"}')
        assert r.status_code == 409
        env.set_on()
        r = await c.put("/api/schedule/off", headers={**ORIGIN, **JSON}, content=b'{"time":"23:00"}')
        assert r.status_code == 200 and r.json()["off"] == "23:00"


async def test_invalid_payloads_are_400(env):
    env.set_off()
    async with env.logged_in() as c:
        for content in (b"no-json", b'{"time":"25:99"}', b'{"time":5}', b"{}", b'{"time":""}'):
            r = await c.put("/api/schedule/on", headers={**ORIGIN, **JSON}, content=content)
            assert r.status_code == 400 and r.json()["reason"] == "invalid_time", content
    assert env.scheduler.on_at is None


async def test_delete_cancels_and_is_idempotent(env):
    env.set_off()
    async with env.logged_in() as c:
        await c.put("/api/schedule/on", headers={**ORIGIN, **JSON}, content=b'{"time":"07:30"}')
        assert (await c.delete("/api/schedule/on", headers=ORIGIN)).status_code == 204
        assert (await c.get("/api/schedule")).json()["on"] is None
        assert (await c.delete("/api/schedule/on", headers=ORIGIN)).status_code == 204
    assert len(env.of("schedule_cancelled")) == 1  # el segundo DELETE no tenía nada que cancelar


async def test_replacing_a_schedule_via_api(env):
    env.set_off()
    async with env.logged_in() as c:
        await c.put("/api/schedule/on", headers={**ORIGIN, **JSON}, content=b'{"time":"07:30"}')
        r = await c.put("/api/schedule/on", headers={**ORIGIN, **JSON}, content=b'{"time":"08:00"}')
        assert r.json()["on"] == "08:00"
