"""Token persistence must degrade gracefully.

Regression: on prod the token file was owned by root while the app runs as
`hermes`, so the post-refresh `write_text` raised PermissionError and crashed
EVERY cron once the hourly access token expired. The persist step is now
best-effort — a write failure logs a warning and the valid in-memory creds are
used for the rest of the run.
"""
import importlib.util

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "google_api_token_under_test",
    "skills/productivity/google-workspace/scripts/google_api.py",
)
g = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(g)


class _FakeCreds:
    def to_json(self):
        return '{"token": "abc", "refresh_token": "xyz", "scopes": ["s"]}'


class _RaisingPath:
    """Stand-in TOKEN_PATH whose write fails like a root-owned file would."""

    def write_text(self, *a, **k):
        raise PermissionError(13, "Permission denied")


def test_persist_failure_does_not_raise(monkeypatch, capsys):
    monkeypatch.setattr(g, "TOKEN_PATH", _RaisingPath())
    # must NOT raise — caller keeps the valid in-memory creds
    g._persist_refreshed_token(_FakeCreds())
    err = capsys.readouterr().err
    assert "could not persist refreshed Google token" in err
    assert "Permission denied" in err


def test_persist_success_writes_normalized_payload(monkeypatch, tmp_path):
    token = tmp_path / "google_token.json"
    monkeypatch.setattr(g, "TOKEN_PATH", token)
    g._persist_refreshed_token(_FakeCreds())
    import json

    data = json.loads(token.read_text())
    assert data["token"] == "abc"
    assert data["type"] == "authorized_user"  # _normalize_* adds this
