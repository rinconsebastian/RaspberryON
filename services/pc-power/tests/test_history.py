import json

from app.history import History, describe


def ev(type, ts=1000.0, **data):
    return {"ts": ts, "type": type, **data}


def test_persists_across_reload(tmp_path):
    p = tmp_path / "e.jsonl"
    h = History(p)
    h.handle(ev("login_ok", ip="1.2.3.4"))
    h.handle(ev("logout", ts=1001.0))
    h2 = History(p)
    assert [r["type"] for r in h2.recent()] == ["logout", "login_ok"]  # más reciente primero


def test_limit_and_order(tmp_path):
    h = History(tmp_path / "e.jsonl")
    for i in range(10):
        h.handle(ev("logout", ts=float(i)))
    assert [r["ts"] for r in h.recent(3)] == [9.0, 8.0, 7.0]


def test_trims_to_1000_and_rotates_file(tmp_path):
    p = tmp_path / "e.jsonl"
    h = History(p, max_events=1000, rotate_at=1200)
    for i in range(1201):
        h.handle(ev("logout", ts=float(i)))
    assert len(h) == 1000
    assert h.recent(1)[0]["ts"] == 1200.0
    assert len(p.read_text().splitlines()) == 1000  # rotado: el archivo no crece sin límite
    assert not p.with_name("e.jsonl.tmp").exists()
    assert len(History(p)) == 1000


def test_event_1001_evicts_oldest(tmp_path):
    h = History(tmp_path / "e.jsonl", max_events=1000, rotate_at=5000)
    for i in range(1001):
        h.handle(ev("logout", ts=float(i)))
    assert len(h) == 1000
    assert min(r["ts"] for r in h.recent(2000)) == 1.0


def test_external_state_change_marking(tmp_path):
    h = History(tmp_path / "e.jsonl", external_window_s=120)
    h.handle(ev("state_change", ts=1000.0, old="on", new="off"))  # sin acción previa
    h.handle(ev("action_accepted", ts=2000.0, action="power_on", source="panel", ip="1.1.1.1"))
    h.handle(ev("state_change", ts=2030.0, old="off", new="on"))  # tras acción reciente
    h.handle(ev("state_change", ts=3000.0, old="on", new="off"))  # mucho después
    ext = {r["ts"]: r["external"] for r in h.recent() if r["type"] == "state_change"}
    assert ext == {1000.0: True, 2030.0: False, 3000.0: True}


def test_only_final_states_are_recorded(tmp_path):
    h = History(tmp_path / "e.jsonl")
    for new in ("starting", "stopping", "checking", "on", "off"):
        h.handle(ev("state_change", old="x", new=new))
    assert [r["new"] for r in h.recent()] == ["off", "on"]


def test_only_whitelisted_fields_are_stored(tmp_path):
    p = tmp_path / "e.jsonl"
    h = History(p)
    h.handle(ev("login_ok", ip="1.2.3.4", code="123456789", token="tok-secreto", cookie="c", password="x"))
    raw = p.read_text()
    for secret in ("123456789", "tok-secreto", "password", "cookie"):
        assert secret not in raw
    assert json.loads(raw)["ip"] == "1.2.3.4"


def test_corrupt_lines_are_skipped(tmp_path):
    p = tmp_path / "e.jsonl"
    p.write_text('{"ts": 1, "type": "logout"}\nbasura\n{"sin":"campos"}\n{"ts": 2, "type": "logout"}\n')
    assert len(History(p)) == 2


def test_descriptions_are_readable_spanish():
    assert describe({"type": "action_accepted", "action": "power_on", "source": "panel", "ip": "1.1.1.1"}) == "Desde el panel: Encender · IP 1.1.1.1"
    assert "externo" in describe({"type": "state_change", "new": "off", "external": True})
    assert describe({"type": "state_change", "new": "on", "external": False}) == "PC encendido"
    assert "5 intentos" in describe({"type": "lockout", "ip": "9.9.9.9", "attempts": 5})
    assert "Navegador nuevo" in describe({"type": "login_ok", "ip": "1.1.1.1"})
    assert describe({"type": "scheduled_off_result", "result": "forced"}) == "Apagado programado: hubo que forzarlo"
