import json

import pytest

from app.sessions import SessionStore, code_matches

DAY = 86400


class Clk:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def setup(tmp_path):
    clk = Clk()
    path = tmp_path / "sessions.json"
    return clk, path, lambda code="codigo-largo-1": SessionStore(path, code, 30, clk)


def test_create_and_validate(setup):
    clk, path, mk = setup
    s = mk()
    tok = s.create()
    assert s.valid(tok)
    assert not s.valid("otro-token")
    assert not s.valid(None) and not s.valid("")


def test_persists_across_restart(setup):
    clk, path, mk = setup
    tok = mk().create()
    assert mk().valid(tok)


def test_expiry_at_30_days(setup):
    clk, path, mk = setup
    s = mk()
    tok = s.create()
    clk.t += 29 * DAY
    assert s.valid(tok)
    assert mk().valid(tok)  # también tras reiniciar
    clk.t += 2 * DAY  # 31 días desde la autorización
    assert not s.valid(tok)
    assert not mk().valid(tok)


def test_expiration_is_fixed_not_sliding(setup):
    clk, path, mk = setup
    s = mk()
    tok = s.create()
    clk.t += 20 * DAY
    assert s.valid(tok)  # usarla no la extiende
    clk.t += 11 * DAY
    assert not s.valid(tok)


def test_code_change_invalidates_all(setup):
    clk, path, mk = setup
    tok = mk("codigo-largo-1").create()
    assert not mk("codigo-largo-2").valid(tok)
    # y no vuelve a valer aunque se restaure el código anterior
    assert not mk("codigo-largo-1").valid(tok)


def test_revoke_one_keeps_others(setup):
    clk, path, mk = setup
    s = mk()
    a, b = s.create(), s.create()
    s.revoke(a)
    assert not s.valid(a) and s.valid(b)
    assert mk().valid(b) and not mk().valid(a)


def test_revoke_all(setup):
    clk, path, mk = setup
    s = mk()
    a, b = s.create(), s.create()
    s.revoke_all()
    assert not s.valid(a) and not s.valid(b)
    assert not mk().valid(a)


def test_file_never_contains_token_or_code(setup):
    clk, path, mk = setup
    s = mk("codigo-largo-1")
    tok = s.create()
    raw = path.read_text()
    assert tok not in raw and "codigo-largo-1" not in raw


def test_atomic_write_leaves_no_tmp(setup):
    clk, path, mk = setup
    s = mk()
    s.create()
    assert not path.with_name(path.name + ".tmp").exists()
    json.loads(path.read_text())


def test_corrupt_file_starts_empty(setup):
    clk, path, mk = setup
    path.write_text("{no es json")
    s = mk()
    assert len(s) == 0
    assert s.valid(s.create())


def test_garbage_session_entries_ignored(setup):
    clk, path, mk = setup
    s = mk()
    tok = s.create()
    data = json.loads(path.read_text())
    data["sessions"]["x"] = "no-numero"
    path.write_text(json.dumps(data))
    s2 = mk()
    assert s2.valid(tok) and len(s2) == 1


def test_code_matches():
    assert code_matches("abc12345", "abc12345")
    assert not code_matches("abc12346", "abc12345")
    assert not code_matches("", "abc12345")
    assert not code_matches("abc12345" * 50, "abc12345")
