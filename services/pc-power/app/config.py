"""Configuración por variables de entorno, validada al arrancar (design D11)."""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(ValueError):
    """Configuración inválida: el servicio no debe arrancar."""


@dataclass(frozen=True)
class Config:
    access_code: str
    pc_host: str
    pc_name: str
    relay_gpio: int
    relay_active_high: bool
    short_pulse_ms: int
    long_pulse_ms: int
    ping_interval_s: float
    transition_timeout_s: float
    session_days: int
    port: int
    relay_driver: str
    state_dir: Path
    cookie_path: str
    cookie_secure: bool
    tz: str
    app_name: str
    ntfy_url: str
    ntfy_token: str
    public_url: str
    off_force_after_min: float
    reminder_after_h: float
    reminder_times: tuple[tuple[int, int], ...]


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} debe ser un entero")


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name} debe ser un número")


def _hhmm_list(raw: str) -> tuple[tuple[int, int], ...]:
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            h, m = part.split(":")
            h, m = int(h), int(m)
        except ValueError:
            raise ConfigError("REMINDER_TIMES debe ser una lista HH:MM separada por comas")
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ConfigError("REMINDER_TIMES contiene una hora fuera de rango")
        out.append((h, m))
    if not out:
        raise ConfigError("REMINDER_TIMES no puede estar vacía")
    return tuple(sorted(set(out)))


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env

    code = env.get("ACCESS_CODE", "")
    if len(code) < 8:
        raise ConfigError("ACCESS_CODE es obligatorio y debe tener al menos 8 caracteres")

    host = env.get("PC_HOST", "").strip()
    try:
        host = str(ipaddress.ip_address(host))
    except ValueError:
        raise ConfigError("PC_HOST es obligatorio y debe ser una dirección IP válida")

    polarity = env.get("RELAY_ACTIVE_HIGH", "").strip().lower()
    if polarity not in ("true", "false"):
        raise ConfigError("RELAY_ACTIVE_HIGH es obligatorio (true o false)")

    gpio = _int(env, "RELAY_GPIO", 23)
    if not 2 <= gpio <= 27:
        raise ConfigError("RELAY_GPIO debe estar entre 2 y 27 (numeración BCM)")

    short_ms = _int(env, "SHORT_PULSE_MS", 500)
    long_ms = _int(env, "LONG_PULSE_MS", 6000)
    if not 0 < short_ms < 2000:
        raise ConfigError("SHORT_PULSE_MS debe ser mayor que 0 y menor que 2000")
    if not 0 < long_ms <= 10000:
        raise ConfigError("LONG_PULSE_MS debe ser mayor que 0 y no superar 10000")

    ping_interval = _float(env, "PING_INTERVAL_S", 3.0)
    if ping_interval <= 0:
        raise ConfigError("PING_INTERVAL_S debe ser positivo")
    timeout = _float(env, "TRANSITION_TIMEOUT_S", 120.0)
    if timeout <= 0:
        raise ConfigError("TRANSITION_TIMEOUT_S debe ser positivo")
    session_days = _int(env, "SESSION_DAYS", 30)
    if session_days <= 0:
        raise ConfigError("SESSION_DAYS debe ser positivo")
    port = _int(env, "PORT", 8101)
    if not 1 <= port <= 65535:
        raise ConfigError("PORT fuera de rango")

    driver = env.get("RELAY_DRIVER", "gpio").strip().lower() or "gpio"
    if driver not in ("gpio", "mock"):
        raise ConfigError("RELAY_DRIVER debe ser gpio o mock")

    state_dir = Path(env.get("STATE_DIRECTORY") or env.get("STATE_DIR") or "./data")

    cookie_path = env.get("COOKIE_PATH", "").strip() or "/pc/"
    if not cookie_path.startswith("/"):
        raise ConfigError("COOKIE_PATH debe empezar por /")
    secure = env.get("COOKIE_SECURE", "true").strip().lower() or "true"
    if secure not in ("true", "false"):
        raise ConfigError("COOKIE_SECURE debe ser true o false")

    tz = env.get("TZ", "").strip() or "America/Bogota"
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ConfigError(f"TZ desconocida: {tz}")

    ntfy_url = env.get("NTFY_URL", "").strip()
    if ntfy_url:
        u = urlparse(ntfy_url)
        if u.scheme not in ("http", "https") or not u.netloc or u.path.strip("/") == "" or "/" in u.path.strip("/"):
            raise ConfigError("NTFY_URL debe tener la forma https://servidor/tema")
    public_url = env.get("PUBLIC_URL", "").strip().rstrip("/")
    if public_url:
        u = urlparse(public_url)
        if u.scheme not in ("http", "https") or not u.netloc or u.path or u.query:
            raise ConfigError("PUBLIC_URL debe ser solo esquema y host, p. ej. https://mi-dominio.duckdns.org")

    force_min = _float(env, "OFF_FORCE_AFTER_MIN", 10.0)
    if not 0 < force_min <= 120:
        raise ConfigError("OFF_FORCE_AFTER_MIN debe estar entre 0 y 120")
    reminder_h = _float(env, "REMINDER_AFTER_H", 4.0)
    if reminder_h <= 0:
        raise ConfigError("REMINDER_AFTER_H debe ser positivo")
    reminder_times = _hhmm_list(env.get("REMINDER_TIMES", "").strip() or "21:00,06:00")

    return Config(
        access_code=code,
        pc_host=host,
        pc_name=(env.get("PC_NAME", "").strip() or "PC"),
        relay_gpio=gpio,
        relay_active_high=polarity == "true",
        short_pulse_ms=short_ms,
        long_pulse_ms=long_ms,
        ping_interval_s=ping_interval,
        transition_timeout_s=timeout,
        session_days=session_days,
        port=port,
        relay_driver=driver,
        state_dir=state_dir,
        cookie_path=cookie_path,
        cookie_secure=secure == "true",
        tz=tz,
        app_name=(env.get("APP_NAME", "").strip() or "Panel"),
        ntfy_url=ntfy_url,
        ntfy_token=env.get("NTFY_TOKEN", "").strip(),
        public_url=public_url,
        off_force_after_min=force_min,
        reminder_after_h=reminder_h,
        reminder_times=reminder_times,
    )
