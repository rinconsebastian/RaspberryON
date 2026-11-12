"""platform/set-env.py: edita el archivo de entorno de la Raspberry sin romper nada."""
import importlib.util
import io
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "platform" / "set-env.py"
spec = importlib.util.spec_from_file_location("set_env", SCRIPT)
set_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(set_env)

BASE = ["# comentario", "ACCESS_CODE=viejo-codigo", "PC_HOST=192.168.10.5", "#NTFY_URL=", "PORT=8101"]


def test_replaces_existing_key_in_place_and_keeps_comments():
    out = set_env.apply(BASE, ["ACCESS_CODE=nuevo-codigo-largo"])
    assert out == ["# comentario", "ACCESS_CODE=nuevo-codigo-largo", "PC_HOST=192.168.10.5", "#NTFY_URL=", "PORT=8101"]


def test_appends_missing_key_without_uncommenting_the_default():
    out = set_env.apply(BASE, ["NTFY_URL=https://ntfy.sh/tema-largo"])
    assert out[:-1] == BASE and out[-1] == "NTFY_URL=https://ntfy.sh/tema-largo"
    assert "#NTFY_URL=" in out  # el ejemplo comentado sigue ahí


def test_deletes_only_the_active_key():
    out = set_env.apply(BASE + ["NTFY_URL=x"], ["-NTFY_URL"])
    assert "NTFY_URL=x" not in out and "#NTFY_URL=" in out


def test_values_with_special_characters_are_kept_literally():
    tricky = "a&b|c/d\\e $HOME `x` \"q\" 'r' #z=1"
    out = set_env.apply(BASE, [f"ACCESS_CODE={tricky}"])
    assert out[1] == f"ACCESS_CODE={tricky}"


def test_multiple_instructions_are_applied_in_order():
    out = set_env.apply(BASE, ["PC_HOST=10.0.0.9", "PC_HOST=10.0.0.10", "RELAY_ACTIVE_HIGH=false", "-PORT"])
    assert "PC_HOST=10.0.0.10" in out and "PC_HOST=10.0.0.9" not in out
    assert "RELAY_ACTIVE_HIGH=false" in out and not any(l.startswith("PORT=") for l in out)


@pytest.mark.parametrize("bad", ["minuscula=1", "1ABC=1", "SIN_IGUAL", "-mal", "A B=1", "=x"])
def test_rejects_invalid_instructions(bad):
    with pytest.raises(ValueError):
        set_env.apply(BASE, [bad])


def test_rejects_newlines_in_values():
    with pytest.raises(ValueError):
        set_env.apply(BASE, ["ACCESS_CODE=uno\ndos"])


def run_main(monkeypatch, capsys, path, stdin):
    monkeypatch.setattr(sys, "argv", ["set-env.py", str(path)])
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    rc = set_env.main()
    return rc, capsys.readouterr()


def test_main_writes_file_and_never_prints_values(tmp_path, monkeypatch, capsys):
    p = tmp_path / "pc-power.env"
    p.write_text("\n".join(BASE) + "\n")
    rc, out = run_main(monkeypatch, capsys, p, "ACCESS_CODE=super-secreto-123\nNTFY_URL=https://ntfy.sh/t\n")
    assert rc == 0
    assert "super-secreto-123" not in out.out + out.err and "ntfy.sh" not in out.out + out.err
    text = p.read_text()
    assert "ACCESS_CODE=super-secreto-123" in text and text.endswith("\n") and "# comentario" in text


def test_main_fails_cleanly_when_file_is_missing(tmp_path, monkeypatch, capsys):
    rc, out = run_main(monkeypatch, capsys, tmp_path / "no-existe.env", "A=1\n")
    assert rc == 1 and "despliega primero" in out.err


def test_main_invalid_input_leaves_the_file_untouched(tmp_path, monkeypatch, capsys):
    p = tmp_path / "pc-power.env"
    p.write_text("\n".join(BASE) + "\n")
    before = p.read_text()
    rc, out = run_main(monkeypatch, capsys, p, "ACCESS_CODE=ok-valor-largo\nmal-formada\n")
    assert rc == 1 and p.read_text() == before  # todo o nada
