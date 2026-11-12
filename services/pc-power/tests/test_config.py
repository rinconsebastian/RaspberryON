import pytest

from app.config import ConfigError, load_config

BASE = {
    "ACCESS_CODE": "codigo-largo-123",
    "PC_HOST": "192.168.10.50",
    "RELAY_ACTIVE_HIGH": "false",
}


def env(**over):
    e = dict(BASE)
    e.update(over)
    return {k: v for k, v in e.items() if v is not None}


def test_defaults():
    c = load_config(env())
    assert c.relay_gpio == 23
    assert c.short_pulse_ms == 500 and c.long_pulse_ms == 6000
    assert c.ping_interval_s == 3 and c.transition_timeout_s == 120
    assert c.session_days == 30 and c.port == 8101
    assert c.relay_active_high is False
    assert c.relay_driver == "gpio"
    assert c.pc_name == "PC"


@pytest.mark.parametrize("code", [None, "", "corto", "1234567"])
def test_access_code_missing_or_short(code):
    with pytest.raises(ConfigError, match="ACCESS_CODE"):
        load_config(env(ACCESS_CODE=code))


def test_access_code_min_length_ok():
    assert load_config(env(ACCESS_CODE="12345678")).access_code == "12345678"


@pytest.mark.parametrize("host", [None, "", "no-es-ip", "192.168.10.999", "1.2.3.4; rm -rf /", "pc.local"])
def test_pc_host_invalid(host):
    with pytest.raises(ConfigError, match="PC_HOST"):
        load_config(env(PC_HOST=host))


def test_pc_host_ipv6_ok():
    assert load_config(env(PC_HOST="fd00::1")).pc_host == "fd00::1"


@pytest.mark.parametrize("v", [None, "", "maybe", "1"])
def test_polarity_required_and_explicit(v):
    with pytest.raises(ConfigError, match="RELAY_ACTIVE_HIGH"):
        load_config(env(RELAY_ACTIVE_HIGH=v))


@pytest.mark.parametrize("v,expected", [("true", True), ("TRUE", True), ("false", False)])
def test_polarity_values(v, expected):
    assert load_config(env(RELAY_ACTIVE_HIGH=v)).relay_active_high is expected


@pytest.mark.parametrize("v", ["10001", "30000", "0", "-5", "abc"])
def test_long_pulse_out_of_range(v):
    with pytest.raises(ConfigError, match="LONG_PULSE_MS"):
        load_config(env(LONG_PULSE_MS=v))


def test_long_pulse_max_ok():
    assert load_config(env(LONG_PULSE_MS="10000")).long_pulse_ms == 10000


@pytest.mark.parametrize("v", ["2000", "5000", "0"])
def test_short_pulse_out_of_range(v):
    with pytest.raises(ConfigError, match="SHORT_PULSE_MS"):
        load_config(env(SHORT_PULSE_MS=v))


def test_short_pulse_just_below_limit_ok():
    assert load_config(env(SHORT_PULSE_MS="1999")).short_pulse_ms == 1999


@pytest.mark.parametrize("name", ["RELAY_GPIO", "PING_INTERVAL_S", "TRANSITION_TIMEOUT_S", "SESSION_DAYS", "PORT"])
def test_non_numeric_rejected(name):
    with pytest.raises(ConfigError, match=name):
        load_config(env(**{name: "x"}))


def test_gpio_range():
    with pytest.raises(ConfigError, match="RELAY_GPIO"):
        load_config(env(RELAY_GPIO="99"))


def test_driver_validation():
    assert load_config(env(RELAY_DRIVER="mock")).relay_driver == "mock"
    with pytest.raises(ConfigError, match="RELAY_DRIVER"):
        load_config(env(RELAY_DRIVER="otro"))


def test_cookie_defaults_and_validation():
    c = load_config(env())
    assert c.cookie_path == "/pc/" and c.cookie_secure is True
    assert load_config(env(COOKIE_PATH="/x/", COOKIE_SECURE="false")).cookie_secure is False
    with pytest.raises(ConfigError, match="COOKIE_PATH"):
        load_config(env(COOKIE_PATH="pc"))
    with pytest.raises(ConfigError, match="COOKIE_SECURE"):
        load_config(env(COOKIE_SECURE="quizas"))


def test_extras_defaults():
    c = load_config(env())
    assert c.tz == "America/Bogota" and c.app_name == "Panel"
    assert c.ntfy_url == "" and c.public_url == ""
    assert c.off_force_after_min == 10 and c.reminder_after_h == 4
    assert c.reminder_times == ((6, 0), (21, 0))


def test_extras_valid_values():
    c = load_config(env(TZ="UTC", NTFY_URL="https://ntfy.sh/mi-tema-largo", NTFY_TOKEN="tk_x",
                        PUBLIC_URL="https://casa.duckdns.org/", REMINDER_TIMES="22:30, 7:05",
                        OFF_FORCE_AFTER_MIN="15", REMINDER_AFTER_H="2.5", APP_NAME="Casa"))
    assert c.tz == "UTC" and c.ntfy_token == "tk_x" and c.app_name == "Casa"
    assert c.public_url == "https://casa.duckdns.org"
    assert c.reminder_times == ((7, 5), (22, 30))
    assert c.off_force_after_min == 15 and c.reminder_after_h == 2.5


@pytest.mark.parametrize("name,val", [
    ("TZ", "Marte/Olimpo"), ("NTFY_URL", "ntfy.sh/tema"), ("NTFY_URL", "https://ntfy.sh"),
    ("NTFY_URL", "https://ntfy.sh/a/b"), ("PUBLIC_URL", "https://x.org/pc"), ("PUBLIC_URL", "ftp://x.org"),
    ("OFF_FORCE_AFTER_MIN", "0"), ("OFF_FORCE_AFTER_MIN", "500"), ("REMINDER_AFTER_H", "0"),
    ("REMINDER_TIMES", "25:00"), ("REMINDER_TIMES", "abc"), ("REMINDER_TIMES", " , "),
])
def test_extras_invalid_values(name, val):
    with pytest.raises(ConfigError, match=name):
        load_config(env(**{name: val}))
