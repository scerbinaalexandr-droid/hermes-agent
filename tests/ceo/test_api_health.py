"""api_health monitor: alerts once on credit failure, throttles the repeat,
stays silent when healthy, and resets on recovery."""
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "api_health_under_test", "skills/ceo/health/scripts/api_health.py")
ah = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ah)


def _point_state_at(tmp_path, monkeypatch):
    monkeypatch.setattr(ah, "STATE_PATH", tmp_path / "cron" / "api_health_state.json")


def test_credit_failure_alerts_then_throttles(monkeypatch, tmp_path, capsys):
    _point_state_at(tmp_path, monkeypatch)
    monkeypatch.setattr(ah, "_probe", lambda: "credit")

    ah.main()
    first = capsys.readouterr().out
    assert "Баланс API" in first
    assert ah.BILLING_URL in first
    assert "402" not in first and "HTTP" not in first  # no technical noise

    # a second run inside the throttle window must stay silent (no spam)
    ah.main()
    assert capsys.readouterr().out.strip() == ""


def test_healthy_is_silent_and_resets(monkeypatch, tmp_path, capsys):
    _point_state_at(tmp_path, monkeypatch)

    # start in a credit outage so there is state to reset
    monkeypatch.setattr(ah, "_probe", lambda: "credit")
    ah.main()
    capsys.readouterr()

    # recover: silent output, state flips back to ok
    monkeypatch.setattr(ah, "_probe", lambda: "ok")
    ah.main()
    assert capsys.readouterr().out.strip() == ""

    import json
    state = json.loads((tmp_path / "cron" / "api_health_state.json").read_text())
    assert state["status"] == "ok"

    # next outage after recovery must alert immediately (not throttled)
    monkeypatch.setattr(ah, "_probe", lambda: "credit")
    ah.main()
    assert "Баланс API" in capsys.readouterr().out


def test_auth_failure_has_clean_message(monkeypatch, tmp_path, capsys):
    _point_state_at(tmp_path, monkeypatch)
    monkeypatch.setattr(ah, "_probe", lambda: "auth")
    ah.main()
    out = capsys.readouterr().out
    assert "ключ" in out.lower()
    assert "HTTP" not in out and "401" not in out
