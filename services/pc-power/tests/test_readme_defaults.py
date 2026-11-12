"""Las tablas del README y deploy/env.example deben coincidir con los valores por defecto reales."""
import re
from pathlib import Path

from app.config import load_config

ROOT = Path(__file__).resolve().parent.parent
BASE = {"ACCESS_CODE": "codigo-largo-123", "PC_HOST": "192.168.10.50", "RELAY_ACTIVE_HIGH": "false"}

# variable -> (atributo de Config, conversión a texto como aparece en el README)
ATTR = {
    "PC_NAME": ("pc_name", str), "RELAY_GPIO": ("relay_gpio", str),
    "SHORT_PULSE_MS": ("short_pulse_ms", str), "LONG_PULSE_MS": ("long_pulse_ms", str),
    "PING_INTERVAL_S": ("ping_interval_s", lambda v: f"{v:g}"),
    "TRANSITION_TIMEOUT_S": ("transition_timeout_s", lambda v: f"{v:g}"),
    "SESSION_DAYS": ("session_days", str), "COOKIE_PATH": ("cookie_path", str),
    "COOKIE_SECURE": ("cookie_secure", lambda v: str(v).lower()), "RELAY_DRIVER": ("relay_driver", str),
    "PORT": ("port", str), "TZ": ("tz", str), "OFF_FORCE_AFTER_MIN": ("off_force_after_min", lambda v: f"{v:g}"),
    "APP_NAME": ("app_name", str), "REMINDER_AFTER_H": ("reminder_after_h", lambda v: f"{v:g}"),
}


def readme_defaults():
    rows = {}
    for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*`([A-Z_]+)`(?: / `([A-Z_]+)`)?\s*\|\s*([^|]+?)\s*\|", line)
        if not m:
            continue
        names = [n for n in (m.group(1), m.group(2)) if n]
        values = [v.strip().strip("`") for v in m.group(3).split(" / ")]
        if len(values) == len(names):  # fila combinada «A / B | `x` / `y`»
            rows.update(zip(names, values))
        else:
            rows[names[0]] = m.group(3).strip().strip("`")
    return rows


def test_readme_table_defaults_match_the_code():
    cfg = load_config(BASE)
    rows = readme_defaults()
    checked = []
    for name, (attr, to_text) in ATTR.items():
        assert name in rows, f"{name} falta en la tabla del README"
        shown = rows[name]
        assert shown == to_text(getattr(cfg, attr)), f"{name}: README dice {shown!r}, el código usa {getattr(cfg, attr)!r}"
        checked.append(name)
    assert len(checked) == len(ATTR)


def test_readme_pulse_pair_and_reminder_times():
    cfg = load_config(BASE)
    rows = readme_defaults()
    assert (rows["SHORT_PULSE_MS"], rows["LONG_PULSE_MS"]) == ("500", "6000")  # fila combinada
    assert rows["REMINDER_TIMES"] == "21:00,06:00"
    assert cfg.reminder_times == ((6, 0), (21, 0))  # el código las ordena; el README las lista en el orden de uso
    assert rows["ACCESS_CODE"].startswith("obligatoria") and rows["PC_HOST"].startswith("obligatoria")


def test_env_example_documents_every_extra_variable_with_correct_defaults():
    text = (ROOT / "deploy" / "env.example").read_text(encoding="utf-8")
    cfg = load_config(BASE)
    expect = {
        "TZ": cfg.tz, "OFF_FORCE_AFTER_MIN": f"{cfg.off_force_after_min:g}", "APP_NAME": cfg.app_name,
        "REMINDER_AFTER_H": f"{cfg.reminder_after_h:g}", "REMINDER_TIMES": "21:00,06:00",
    }
    for name, value in expect.items():
        m = re.search(rf"^#?{name}=(.*)$", text, re.M)
        assert m, f"{name} no está en env.example"
        assert m.group(1) == value, f"env.example: {name}={m.group(1)!r}, el código usa {value!r}"
    for name in ("NTFY_URL", "NTFY_TOKEN", "PUBLIC_URL"):
        assert re.search(rf"^#?{name}=", text, re.M), f"{name} no está en env.example"
