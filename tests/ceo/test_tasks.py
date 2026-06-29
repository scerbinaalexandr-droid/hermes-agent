"""tasks_list helper: deadline parsing + open-task bucketing (Google mocked)."""
import datetime as dt
import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "tasks_list_under_test", "skills/ceo/tasks/scripts/tasks_list.py")
tl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tl)

TODAY = dt.date(2026, 6, 29)
HEADER = ["task_id", "note_id", "Дата", "Направление", "Встреча", "Задача",
          "Ответственный", "Срок", "Статус", "Создано"]


def test_parse_due_formats():
    assert tl._parse_due("2026-07-01", TODAY) == dt.date(2026, 7, 1)
    assert tl._parse_due("до 27.06.2026", TODAY) == dt.date(2026, 6, 27)
    assert tl._parse_due("01.07", TODAY) == dt.date(2026, 7, 1)
    assert tl._parse_due("до пятницы", TODAY) is None
    assert tl._parse_due("", TODAY) is None


def test_parse_due_bare_ddmm_current_year():
    # bare dd.mm → current year (overdue surfaces, never silently rolled forward)
    assert tl._parse_due("01.07", TODAY) == dt.date(2026, 7, 1)
    assert tl._parse_due("20.06", TODAY) == dt.date(2026, 6, 20)


def _rows():
    return [
        HEADER,
        ["t1", "", "", "Finance", "Заметка", "Просроченная", "CFO", "2026-06-20", "open", ""],
        ["t2", "", "", "Sport", "Заметка", "Скоро", "Я", "2026-07-01", "open", ""],
        ["t3", "", "", "", "Заметка", "Без срока", "", "до пятницы", "open", ""],
        ["t4", "", "", "", "Заметка", "Сделанная", "", "2026-06-20", "done", ""],   # excluded
        ["t5", "", "", "", "Заметка", "", "", "", "open", ""],                       # empty task → skip
    ]


def test_cmd_list_buckets(monkeypatch):
    monkeypatch.setenv("HERMES_MEETING_SHEET_ID", "SID")
    monkeypatch.setattr(tl, "_today", lambda: TODAY)
    import skills.ceo._lib.sheets_meeting_sync as sms

    class FakeGW:
        def __init__(self, *a, **k):
            pass

        def get(self, sid, rng):
            return _rows()
    monkeypatch.setattr(sms, "GoogleApiGW", FakeGW)

    res = tl.cmd_list()
    assert res["ok"] and res["total_open"] == 3
    assert len(res["overdue"]) == 1 and res["overdue"][0]["task"] == "Просроченная"
    assert res["overdue"][0]["overdue_days"] == 9
    assert len(res["soon"]) == 1 and res["soon"][0]["task"] == "Скоро"
    assert len(res["later"]) == 1 and res["later"][0]["task"] == "Без срока"


def test_cmd_list_no_sheet(monkeypatch):
    monkeypatch.delenv("HERMES_MEETING_SHEET_ID", raising=False)
    assert tl.cmd_list()["ok"] is False
