"""calendar_create event-body building: recurrence + reminders + timezone.

Google API is mocked (no network); we assert the request body the helper builds.
"""
import importlib.util
import types

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "google_api_under_test",
    "skills/productivity/google-workspace/scripts/google_api.py",
)
g = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(g)


class _FakeEvents:
    captured = None

    def insert(self, calendarId, body):
        _FakeEvents.captured = body

        class _R:
            def execute(self_inner):
                return {"id": "evt1", "summary": body.get("summary", ""), "htmlLink": "http://x"}

        return _R()


class _FakeSvc:
    def events(self):
        return _FakeEvents()


@pytest.fixture(autouse=True)
def _mock_service(monkeypatch):
    monkeypatch.setattr(g, "_gws_binary", lambda: False)
    monkeypatch.setattr(g, "build_service", lambda *a, **k: _FakeSvc())
    _FakeEvents.captured = None


def _args(**over):
    base = dict(summary="M", start="2026-06-30T10:00:00+03:00", end="2026-06-30T11:00:00+03:00",
                location="", description="", attendees="", recurrence="", reminders="",
                timezone="", calendar="primary")
    base.update(over)
    return types.SimpleNamespace(**base)


def test_recurrence_and_reminders_built(capsys):
    g.calendar_create(_args(recurrence="FREQ=WEEKLY;BYDAY=MO", reminders="60,1440"))
    b = _FakeEvents.captured
    assert b["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO"]
    assert b["reminders"]["overrides"] == [
        {"method": "popup", "minutes": 60}, {"method": "popup", "minutes": 1440}]


def test_recurring_event_gets_default_timezone(capsys):
    # recurring REQUIRES a tz; absent --timezone we default to Europe/Chisinau
    g.calendar_create(_args(recurrence="FREQ=WEEKLY;BYDAY=MO"))
    b = _FakeEvents.captured
    assert b["start"]["timeZone"] == "Europe/Chisinau"
    assert b["end"]["timeZone"] == "Europe/Chisinau"


def test_explicit_timezone_wins(capsys):
    g.calendar_create(_args(recurrence="FREQ=WEEKLY;BYDAY=MO", timezone="Europe/Bucharest"))
    assert _FakeEvents.captured["start"]["timeZone"] == "Europe/Bucharest"


def test_single_event_no_timezone_unless_given(capsys):
    # non-recurring + no --timezone → no timeZone field (preserve old behavior)
    g.calendar_create(_args())
    b = _FakeEvents.captured
    assert "timeZone" not in b["start"] and "recurrence" not in b
