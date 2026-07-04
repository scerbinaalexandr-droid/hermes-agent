"""evening/week reviews must land on the persistent volume, not the ephemeral
in-image dir — otherwise every review is silently wiped on redeploy (and the
evening skill never sees the day's brief). Verify _logs_root() honours
HERMES_CEO_MEMORY_ROOT the same way diary.py does.
"""
import importlib.util


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_evening_logs_root_follows_memory_root(monkeypatch, tmp_path):
    ev = _load("skills/ceo/evening/scripts/record_evening.py", "rec_evening_ut")
    monkeypatch.setenv("HERMES_CEO_MEMORY_ROOT", str(tmp_path / "opt" / "data" / "memory"))
    root = ev._logs_root()
    assert root == (tmp_path / "opt" / "data" / "logs")
    assert "opt/hermes" not in str(root)  # not the ephemeral in-image dir


def test_week_logs_root_follows_memory_root(monkeypatch, tmp_path):
    wk = _load("skills/ceo/week/scripts/record_week.py", "rec_week_ut")
    monkeypatch.setenv("HERMES_CEO_MEMORY_ROOT", str(tmp_path / "opt" / "data" / "memory"))
    root = wk._logs_root()
    assert root == (tmp_path / "opt" / "data" / "logs")


def test_logs_root_falls_back_to_hermes_home(monkeypatch, tmp_path):
    ev = _load("skills/ceo/evening/scripts/record_evening.py", "rec_evening_ut2")
    monkeypatch.delenv("HERMES_CEO_MEMORY_ROOT", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    assert ev._logs_root() == (tmp_path / "home" / "logs")
