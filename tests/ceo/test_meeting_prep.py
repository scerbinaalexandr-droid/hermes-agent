"""meeting_prep helper: cmd_save input validation + tz resolution (offline)."""
import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "meeting_prep_under_test", "skills/ceo/prep/scripts/meeting_prep.py")
mp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mp)


def test_cmd_save_rejects_non_dict_payload():
    assert mp.cmd_save(["not", "a", "dict"])["reason"] == "payload-not-dict"


def test_cmd_save_rejects_non_list_meetings():
    assert mp.cmd_save({"meetings": "oops"})["reason"] == "meetings-not-list"


def test_cmd_save_no_sheet_configured(monkeypatch):
    monkeypatch.delenv("HERMES_MEETING_SHEET_ID", raising=False)
    res = mp.cmd_save({"meetings": [{"title": "x"}]})
    assert res["saved"] is False and res["reason"] == "no-sheet-configured"


def test_cmd_save_invalid_item_does_not_crash(monkeypatch):
    # a non-dict meeting item must be skipped, not raise AttributeError
    monkeypatch.setenv("HERMES_MEETING_SHEET_ID", "SID")

    def boom(*a, **k):
        raise AssertionError("sync_meeting should not be reached for invalid item")
    # patch the lazily-imported symbol so a bad item never reaches sync
    import skills.ceo._lib.sheets_meeting_sync as sms
    monkeypatch.setattr(sms, "sync_meeting", boom)
    res = mp.cmd_save({"meetings": ["bad-item"]})
    assert res["saved"] is True and res["count"] == 0
    assert res["results"][0]["reason"] == "invalid-meeting-item"


def test_today_bounds_returns_iso():
    date, start, end = mp._today_bounds()
    assert len(date) == 10 and "T" in start and "T" in end
