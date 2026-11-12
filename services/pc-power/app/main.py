"""API y páginas del servicio (design D5, D6, D9). Rutas relativas al prefijo /pc/."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Config, ConfigError, load_config
from .control import Outcome, PowerController
from .events import EventBus
from .history import History
from .monitor import Monitor
from .notifier import Notifier
from .power import Action, PowerMachine
from .ratelimit import AttemptLimiter, client_ip
from .relay import GpioDriver, MockDriver, Relay
from .reminder import Reminders
from .schedule import ScheduleError, Scheduler
from .sessions import SessionStore, code_matches

log = logging.getLogger("pc-power")

COOKIE = "pcp_session"
GENERIC_MESSAGE = "Solicitud recibida."
LOGIN_DELAY_S = 0.8
MAX_BODY = 2048
STATIC = Path(__file__).resolve().parent.parent / "static"
PUBLIC_ICONS = ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png")

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex",
}


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def same_origin(request: Request) -> bool:
    """Acepta solo peticiones cuyo origen es el propio sitio (design D9).

    Sec-Fetch-Site lo fija el navegador y la página no puede falsificarlo, así que manda
    cuando existe (con Referrer-Policy estricta, Chrome envía `Origin: null` en los
    formularios). Sin él se compara la cabecera Origin con el Host."""
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site == "same-origin"
    origin = request.headers.get("origin")
    if origin:
        return urlparse(origin).netloc == request.headers.get("host", "")
    return False


def not_found() -> Response:
    return Response(status_code=404)


def create_app(
    cfg: Config,
    relay: Relay,
    machine: PowerMachine,
    store: SessionStore,
    limiter: AttemptLimiter,
    monitor: Monitor | None = None,
    login_delay_s: float = LOGIN_DELAY_S,
    *,
    bus: EventBus | None = None,
    history: History | None = None,
    controller: PowerController | None = None,
    notifier: Notifier | None = None,
    scheduler: Scheduler | None = None,
    reminders: Reminders | None = None,
) -> FastAPI:
    bus = bus or EventBus()
    machine.emit = bus.emit
    if history is not None:
        bus.subscribe(history.handle)
    if notifier is not None and notifier.enabled:
        bus.subscribe(notifier.handle)
    controller = controller or PowerController(cfg, relay, machine, bus)

    app_name = html.escape(cfg.app_name)
    login_html = _read("login.html").replace("{{APP_NAME}}", app_name)
    panel_html = _read("panel.html").replace("{{NAME}}", html.escape(cfg.pc_name)).replace("{{APP_NAME}}", app_name)
    app_css = _read("app.css")
    panel_js = _read("panel.js")
    sw_js = _read("sw.js")
    sw_register_js = _read("sw-register.js")
    icons = {n: (STATIC / "icons" / n).read_bytes() for n in PUBLIC_ICONS}
    manifest = json.dumps(
        {
            "name": cfg.app_name,
            "short_name": cfg.app_name,
            "start_url": "./",
            "scope": "./",
            "display": "standalone",
            "background_color": "#0f1216",
            "theme_color": "#1d4ed8",
            "icons": [
                {"src": "static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                {"src": "static/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            ],
        },
        ensure_ascii=False,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bg = []
        if monitor:
            bg.append(asyncio.create_task(monitor.run()))
        if notifier is not None and notifier.enabled:
            bg.append(asyncio.create_task(notifier.run()))
        if scheduler is not None:
            bg.append(asyncio.create_task(scheduler.run()))
        if reminders is not None:
            bg.append(asyncio.create_task(reminders.run()))
        try:
            yield
        finally:
            for t in bg:
                t.cancel()
            controller.shutdown()
            relay.close()  # el relé siempre queda abierto al parar

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.bus = bus

    # ---- respuestas uniformes ---------------------------------------------
    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        # 404 y 405 se ven igual: no se revela qué rutas existen
        return Response(status_code=404 if exc.status_code in (404, 405) else exc.status_code)

    @app.middleware("http")
    async def _headers(request: Request, call_next):
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers[k] = v
        if "server" in response.headers:
            del response.headers["server"]
        return response

    def token_of(request: Request) -> str | None:
        return request.cookies.get(COOKIE)

    def authorized(request: Request) -> bool:
        return store.valid(token_of(request))

    def clear_cookie(response: Response) -> None:
        response.delete_cookie(COOKIE, path=cfg.cookie_path)

    # ---- páginas -----------------------------------------------------------
    @app.get("/")
    async def index(request: Request):
        if authorized(request):
            return Response(panel_html, media_type="text/html; charset=utf-8")
        msg = f'<p class="note">{GENERIC_MESSAGE}</p>' if request.query_params.get("s") == "1" else ""
        return Response(login_html.replace("{{MSG}}", msg), media_type="text/html; charset=utf-8")

    @app.get("/static/app.css")
    async def css():
        return Response(app_css, media_type="text/css; charset=utf-8")

    # Instalación como app: todo público y neutro (el navegador los pide sin sesión)
    @app.get("/manifest.webmanifest")
    async def manifest_json():
        return Response(manifest, media_type="application/manifest+json")

    @app.get("/sw.js")
    async def service_worker():
        return Response(sw_js, media_type="text/javascript; charset=utf-8")

    @app.get("/static/sw-register.js")
    async def sw_register():
        return Response(sw_register_js, media_type="text/javascript; charset=utf-8")

    @app.get("/static/icons/{name}")
    async def icon(name: str):
        data = icons.get(name)
        return Response(data, media_type="image/png") if data else not_found()

    @app.get("/static/panel.js")
    async def js(request: Request):
        if not authorized(request):
            return not_found()
        return Response(panel_js, media_type="text/javascript; charset=utf-8")

    # ---- login (respuesta idéntica en acierto, fallo, vacío y bloqueo) -------
    @app.post("/login")
    async def login(request: Request):
        started = time.monotonic()
        ok = False
        ip = client_ip(request.client.host if request.client else None, request.headers.get("x-forwarded-for"))
        if same_origin(request):
            if not limiter.blocked(ip):
                raw = (await request.body())[:MAX_BODY].decode("utf-8", "replace")
                code = parse_qs(raw).get("code", [""])[0]
                if code and code_matches(code, cfg.access_code):
                    ok = True
                else:
                    if limiter.record_failure(ip):
                        log.warning("bloqueo por intentos fallidos desde %s", ip)
                        bus.emit("lockout", ip=ip, attempts=limiter.ip_max)
        # Tiempo de respuesta fijo: no depende del resultado ni de la longitud del código
        remaining = login_delay_s - (time.monotonic() - started)
        if remaining > 0:
            await asyncio.sleep(remaining)
        response = RedirectResponse("./?s=1", status_code=303)
        if ok:
            bus.emit("login_ok", ip=ip)
            response.set_cookie(
                COOKIE,
                store.create(),
                max_age=cfg.session_days * 86400,
                path=cfg.cookie_path,
                httponly=True,
                secure=cfg.cookie_secure,
                samesite="strict",
            )
        return response

    # ---- API (404 sin sesión; el origen se valida en los POST) --------------
    @app.get("/api/status")
    async def status(request: Request):
        if not authorized(request):
            return not_found()
        snap = machine.snapshot()
        snap.update(busy=relay.busy, name=cfg.pc_name)
        if scheduler is not None:
            snap["schedule"] = scheduler.status()
        return JSONResponse(snap)

    @app.post("/api/action")
    async def action(request: Request):
        if not authorized(request):
            return not_found()
        if not same_origin(request):
            return Response(status_code=403)
        try:
            body = json.loads((await request.body())[:MAX_BODY] or b"{}")
            act = Action(body.get("type"))
        except (ValueError, AttributeError, TypeError):
            return JSONResponse({"reason": "bad_action"}, status_code=400)
        ip = client_ip(request.client.host if request.client else None, request.headers.get("x-forwarded-for"))
        result = controller.request(act, "panel", ip)  # síncrono: comprobar estado y reservar el relé es atómico
        if result.outcome is Outcome.BUSY:
            return JSONResponse({"reason": "busy"}, status_code=409)
        if result.outcome is Outcome.INVALID_STATE:
            return JSONResponse({"reason": "invalid_state", "state": result.state}, status_code=409)
        return JSONResponse({"ok": True, "pulse_ms": result.pulse_ms}, status_code=202)

    @app.get("/api/events")
    async def events(request: Request):
        if not authorized(request):
            return not_found()
        try:
            limit = max(1, min(200, int(request.query_params.get("limit", "50"))))
        except ValueError:
            limit = 50
        return JSONResponse(history.recent(limit) if history else [])

    # ---- enlaces de los recordatorios: única acción sin sesión (design D9) --------------------
    # El token de 256 bits y un solo uso hace de credencial; todo fallo es un 404 vacío idéntico.
    @app.post("/r/{token}/{kind}")
    async def reminder_link(token: str, kind: str, request: Request):
        if reminders is None or kind not in ("off", "keep") or not reminders.rate_ok():
            return not_found()
        ip = client_ip(request.client.host if request.client else None, request.headers.get("x-forwarded-for"))
        code = reminders.consume(token, kind, ip)
        if code == 204:
            return Response(status_code=204)
        if code == 409:
            return JSONResponse({"reason": "busy"}, status_code=409)
        return not_found()

    # ---- programación de encendido / apagado únicos -------------------------------
    @app.get("/api/schedule")
    async def schedule_get(request: Request):
        if scheduler is None or not authorized(request):
            return not_found()
        return JSONResponse(scheduler.status())

    @app.put("/api/schedule/{kind}")
    async def schedule_put(kind: str, request: Request):
        if scheduler is None or kind not in ("on", "off") or not authorized(request):
            return not_found()
        if not same_origin(request):
            return Response(status_code=403)
        try:
            body = json.loads((await request.body())[:MAX_BODY] or b"{}")
            hhmm = body.get("time")
        except (ValueError, AttributeError):
            return JSONResponse({"reason": "invalid_time"}, status_code=400)
        try:
            return JSONResponse(scheduler.set(kind, hhmm))
        except ScheduleError as exc:
            return JSONResponse({"reason": exc.code}, status_code=409 if exc.code == "invalid_state" else 400)

    @app.delete("/api/schedule/{kind}")
    async def schedule_delete(kind: str, request: Request):
        if scheduler is None or kind not in ("on", "off") or not authorized(request):
            return not_found()
        if not same_origin(request):
            return Response(status_code=403)
        scheduler.cancel(kind)
        return Response(status_code=204)

    @app.post("/api/logout")
    async def logout(request: Request):
        if not authorized(request):
            return not_found()
        if not same_origin(request):
            return Response(status_code=403)
        store.revoke(token_of(request))
        bus.emit("logout")
        response = Response(status_code=204)
        clear_cookie(response)
        return response

    @app.post("/api/logout-all")
    async def logout_all(request: Request):
        if not authorized(request):
            return not_found()
        if not same_origin(request):
            return Response(status_code=403)
        store.revoke_all()
        bus.emit("logout_all")
        response = Response(status_code=204)
        clear_cookie(response)
        return response

    return app


def build(cfg: Config) -> FastAPI:
    if cfg.relay_driver == "gpio":
        driver = GpioDriver(cfg.relay_gpio, cfg.relay_active_high)
    else:
        driver = MockDriver()
    relay = Relay(driver)
    machine = PowerMachine(transition_timeout_s=cfg.transition_timeout_s)
    store = SessionStore(cfg.state_dir / "sessions.json", cfg.access_code, cfg.session_days)
    limiter = AttemptLimiter()
    monitor = Monitor(cfg.pc_host, cfg.ping_interval_s, machine)
    bus = EventBus()
    machine.emit = bus.emit
    controller = PowerController(cfg, relay, machine, bus)
    history = History(cfg.state_dir / "events.jsonl", external_window_s=cfg.transition_timeout_s + 30)
    scheduler = Scheduler(cfg, machine, controller, bus, cfg.state_dir / "schedule.json")
    notifier = (
        Notifier(cfg.ntfy_url, cfg.ntfy_token, cfg.tz, suppress_no_effect=lambda: scheduler.quiet)
        if cfg.ntfy_url
        else None
    )
    reminders = (
        Reminders(cfg, machine, notifier, controller, bus, cfg.state_dir / "reminders.json")
        if notifier is not None
        else None
    )
    return create_app(
        cfg, relay, machine, store, limiter, monitor,
        bus=bus, history=history, controller=controller, notifier=notifier, scheduler=scheduler,
        reminders=reminders,
    )


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"ERROR de configuración: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
    import uvicorn

    app = build(cfg)
    # Un solo worker (el cerrojo del relé y el estado viven en memoria) y solo en loopback.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=cfg.port,
        workers=1,
        server_header=False,
        date_header=False,
        access_log=False,
        proxy_headers=False,
    )
