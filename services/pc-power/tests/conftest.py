import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from app.config import load_config
from app.control import PowerController
from app.schedule import Scheduler
from app.events import EventBus
from app.history import History
from app.main import create_app
from app.power import PowerMachine
from app.ratelimit import AttemptLimiter
from app.relay import MockDriver, Relay
from app.sessions import SessionStore

CODE = "codigo-largo-123"
ORIGIN = {"Origin": "https://testserver"}


class Env:
    """Aplicación completa con relé simulado cuyos pulsos duran 0 s reales."""

    def __init__(self, tmp_path, login_delay_s=0.0, cooldown_s=0.0, block_pulse=False, cookie_path="/", extra_env=None):
        self.cfg = load_config(
            {
                "ACCESS_CODE": CODE,
                "PC_HOST": "192.168.10.50",
                "RELAY_ACTIVE_HIGH": "false",
                "RELAY_DRIVER": "mock",
                "STATE_DIR": str(tmp_path),
                "PC_NAME": "Mi PC",
                "COOKIE_PATH": cookie_path,
                **(extra_env or {}),
            }
        )
        self.driver = MockDriver()
        self.durations: list[float] = []
        self.gate = asyncio.Event()
        if not block_pulse:
            self.gate.set()

        async def fake_sleep(seconds):
            self.durations.append(seconds)
            await self.gate.wait()

        self.relay = Relay(self.driver, cooldown_s=cooldown_s, sleep=fake_sleep)
        self.machine = PowerMachine()
        self.bus = EventBus()
        self.events = []
        self.bus.subscribe(self.events.append)
        self.history = History(tmp_path / 'events.jsonl')
        self.machine.emit = self.bus.emit
        self.controller = PowerController(self.cfg, self.relay, self.machine, self.bus)
        self.scheduler = Scheduler(self.cfg, self.machine, self.controller, self.bus, tmp_path / 'schedule.json')
        self.store = SessionStore(tmp_path / "sessions.json", CODE, 30)
        self.limiter = AttemptLimiter()
        self.app = create_app(
            self.cfg, self.relay, self.machine, self.store, self.limiter, None,
            login_delay_s=login_delay_s, bus=self.bus, history=self.history,
            controller=self.controller, scheduler=self.scheduler,
        )

    def of(self, type):
        return [e for e in self.events if e['type'] == type]

    def set_on(self):
        self.machine.on_ping(True)

    def set_off(self):
        for _ in range(3):
            self.machine.on_ping(False)

    @asynccontextmanager
    async def client(self, ip="127.0.0.1", forwarded=None):
        transport = httpx.ASGITransport(app=self.app, client=(ip, 5555))
        headers = {"X-Forwarded-For": forwarded} if forwarded else {}
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver", headers=headers) as c:
            yield c

    @asynccontextmanager
    async def logged_in(self, **kw):
        async with self.client(**kw) as c:
            r = await c.post("/login", data={"code": CODE}, headers=ORIGIN)
            assert r.status_code == 303
            yield c


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


@pytest.fixture
def make_env(tmp_path):
    return lambda **kw: Env(tmp_path, **kw)
