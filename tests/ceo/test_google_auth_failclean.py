"""Google-dependent no_agent crons must fail CLEAN when the OAuth token is
expired/revoked — one throttled human line (or silence), never a raw
google.auth traceback that the scheduler wraps as a cron error.

Regression guard for the 2026-07-06 outage: a revoked refresh token crashed
both 🎂 birthday jobs and the inbox triage twice a day."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_GWS = _ROOT / "skills" / "productivity" / "google-workspace" / "scripts"
sys.path.insert(0, str(_GWS))
import google_api as gws  # noqa: E402


def _load(rel_path, name):
    spec = importlib.util.spec_from_file_location(name, str(_ROOT / rel_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


birthday = _load("skills/ceo/birthday/scripts/birthday.py", "birthday_under_test")
inbox = _load("skills/ceo/inbox/scripts/inbox_triage.py", "inbox_under_test")


def _raise_auth():
    raise gws.GoogleAuthError("('invalid_grant: Token has been expired or revoked.', ...)")


def _raise_generic():
    raise RuntimeError("Gmail API returned 500")


def _install_fake_google(monkeypatch, *, refresh_error):
    """Stub the google.* modules get_credentials imports lazily, so the real
    build_service→get_credentials→refresh path can be exercised without the
    google client libs installed."""
    class RefreshError(Exception):
        pass

    class TransportError(Exception):
        pass

    class Credentials:
        def __init__(self):
            self.expired = True
            self.refresh_token = "x"
            self.valid = False

        @classmethod
        def from_authorized_user_file(cls, path, scopes):
            return cls()

        def refresh(self, request):
            if refresh_error:
                raise RefreshError("('invalid_grant: Token has been expired or revoked.', ...)")
            self.valid = True

        def to_json(self):
            return '{"token": "x", "refresh_token": "x", "type": "authorized_user"}'

    for name in ("google", "google.oauth2", "google.oauth2.credentials", "google.auth",
                 "google.auth.transport", "google.auth.transport.requests",
                 "google.auth.exceptions"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    sys.modules["google.oauth2.credentials"].Credentials = Credentials
    sys.modules["google.auth.transport.requests"].Request = lambda: object()
    sys.modules["google.auth.exceptions"].RefreshError = RefreshError
    sys.modules["google.auth.exceptions"].TransportError = TransportError


def test_alert_throttles_and_resets(tmp_path, monkeypatch):
    monkeypatch.setattr(gws, "_GOOGLE_DOWN_STATE", tmp_path / "google_auth_state.json")
    first = gws.google_down_alert()
    assert first and "Google" in first
    assert "Traceback" not in first and "invalid_grant" not in first  # clean
    assert gws.google_down_alert() is None            # throttled inside window
    gws._clear_google_down_state()
    assert gws.google_down_alert() is not None         # recovery → alerts again


def test_birthday_check_fails_clean(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gws, "_GOOGLE_DOWN_STATE", tmp_path / "s.json")
    monkeypatch.setattr(birthday, "_svc", _raise_auth)
    monkeypatch.setattr(sys, "argv", ["birthday.py"])   # bare → --check (the cron)
    rc = birthday.main()
    out = capsys.readouterr().out
    assert rc == 0                                      # never a nonzero cron error
    assert "Google" in out
    assert "Traceback" not in out and "invalid_grant" not in out


def test_birthday_check_silent_when_throttled(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gws, "_GOOGLE_DOWN_STATE", tmp_path / "s.json")
    gws.google_down_alert()          # a sibling job already alerted → throttle set
    capsys.readouterr()
    monkeypatch.setattr(birthday, "_svc", _raise_auth)
    monkeypatch.setattr(sys, "argv", ["birthday.py"])
    rc = birthday.main()
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""        # throttled → no twice-a-day spam


def test_birthday_add_gives_actionable_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gws, "_GOOGLE_DOWN_STATE", tmp_path / "s.json")
    monkeypatch.setattr(birthday, "_svc", _raise_auth)
    monkeypatch.setattr(
        sys, "argv",
        ["birthday.py", "--add", "--name", "Маша", "--day", "1", "--month", "1"],
    )
    rc = birthday.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "переавториз" in out.lower()                 # interactive → always actionable
    assert "Traceback" not in out


def test_inbox_triage_fails_clean(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gws, "_GOOGLE_DOWN_STATE", tmp_path / "s.json")
    monkeypatch.setattr(inbox, "_svc", _raise_auth)
    monkeypatch.setattr(sys, "argv", ["inbox_triage.py"])
    rc = inbox.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "Google" in out
    assert "Traceback" not in out and "invalid_grant" not in out


# --- exercises the real refresh path (Codex finding #6) ---

def test_get_credentials_maps_refresh_error(tmp_path, monkeypatch):
    token = tmp_path / "google_token.json"
    token.write_text("{}")
    monkeypatch.setattr(gws, "TOKEN_PATH", token)
    monkeypatch.setattr(gws, "_stored_token_scopes", lambda: list(gws.SCOPES))
    _install_fake_google(monkeypatch, refresh_error=True)
    with pytest.raises(gws.GoogleAuthError):   # RefreshError → clean typed error
        gws.get_credentials()


def test_get_credentials_ok_resets_throttle(tmp_path, monkeypatch):
    state = tmp_path / "google_auth_state.json"
    state.write_text('{"ts": 9999999999}')     # a prior outage left the throttle set
    monkeypatch.setattr(gws, "_GOOGLE_DOWN_STATE", state)
    token = tmp_path / "google_token.json"
    token.write_text("{}")
    monkeypatch.setattr(gws, "TOKEN_PATH", token)
    monkeypatch.setattr(gws, "_stored_token_scopes", lambda: list(gws.SCOPES))
    _install_fake_google(monkeypatch, refresh_error=False)
    creds = gws.get_credentials()
    assert creds.valid
    assert not state.exists()                   # recovery → next outage alerts at once


def test_ensure_authenticated_missing_token_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(gws, "TOKEN_PATH", tmp_path / "nope.json")
    with pytest.raises(gws.GoogleAuthError):     # not sys.exit → crons can fail clean
        gws._ensure_authenticated()


# --- non-auth failures (Codex finding #2): 401 at .execute(), API 5xx, network ---

def test_birthday_check_silent_on_generic_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gws, "_GOOGLE_DOWN_STATE", tmp_path / "s.json")
    monkeypatch.setattr(birthday, "_svc", _raise_generic)
    monkeypatch.setattr(sys, "argv", ["birthday.py"])
    rc = birthday.main()
    cap = capsys.readouterr()
    assert rc == 0
    assert cap.out.strip() == ""                # no delivery on a transient error
    assert "Traceback" not in cap.out
    assert "check failed" in cap.err            # detail goes to logs, not the user


def test_birthday_add_reraises_generic_error(tmp_path, monkeypatch):
    monkeypatch.setattr(gws, "_GOOGLE_DOWN_STATE", tmp_path / "s.json")
    monkeypatch.setattr(birthday, "_svc", _raise_generic)
    monkeypatch.setattr(
        sys, "argv",
        ["birthday.py", "--add", "--name", "X", "--day", "1", "--month", "1"],
    )
    with pytest.raises(RuntimeError):            # interactive → surface the real error
        birthday.main()


def test_inbox_silent_on_generic_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gws, "_GOOGLE_DOWN_STATE", tmp_path / "s.json")
    monkeypatch.setattr(inbox, "_svc", _raise_generic)
    monkeypatch.setattr(sys, "argv", ["inbox_triage.py"])
    rc = inbox.main()
    cap = capsys.readouterr()
    assert rc == 0
    assert cap.out.strip() == ""
    assert "triage failed" in cap.err
