"""morning ritual helper: meditation rotation + focus read/save (Google mocked)."""
import datetime as dt
import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "morning_under_test", "skills/ceo/morning/scripts/morning.py")
mo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mo)


def test_meditation_deterministic_rotation():
    d1 = dt.date(2026, 6, 29)
    assert mo._meditation_for(d1) == mo._meditation_for(d1)  # stable for a given day
    # rotates across the set
    seen = {mo._meditation_for(d1 + dt.timedelta(days=i)) for i in range(len(mo._MEDITATIONS))}
    assert len(seen) == len(mo._MEDITATIONS)


def test_gather_no_sheet(monkeypatch):
    monkeypatch.delenv("HERMES_MEETING_SHEET_ID", raising=False)
    out = mo.cmd_gather()
    assert out["count"] == 0 and out["meditation"] and out["reason"] == "no-sheet-configured"


def test_gather_reads_focus(monkeypatch):
    monkeypatch.setenv("HERMES_MEETING_SHEET_ID", "SID")
    import skills.ceo._lib.sheets_meeting_sync as sms

    class FakeGW:
        def __init__(self, *a, **k):
            pass

        def get(self, sid, rng):
            return [["focus_id", "Дата", "Фокус", "Создано"],
                    ["f1", "2026-06-29", "Я спокоен и собран", "x"],
                    ["f2", "2026-06-29", "Фокус на главном", "x"],
                    ["f3", "2026-06-29", "", "x"]]  # blank → skipped
    monkeypatch.setattr(sms, "GoogleApiGW", FakeGW)
    out = mo.cmd_gather()
    assert out["count"] == 2 and out["focus"] == ["Я спокоен и собран", "Фокус на главном"]


def test_save_validation(monkeypatch):
    monkeypatch.delenv("HERMES_MEETING_SHEET_ID", raising=False)
    assert mo.cmd_save({"text": ""})["reason"] == "empty"
    assert mo.cmd_save("nope")["reason"] == "payload-not-dict"
    assert mo.cmd_save({"text": "x"})["reason"] == "no-sheet-configured"
