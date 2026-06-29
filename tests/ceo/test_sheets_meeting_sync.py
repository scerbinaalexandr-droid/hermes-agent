"""Unit tests for meeting → Sheets sync. Google is mocked; no network calls."""
import json
import subprocess

import pytest

from skills.ceo._lib import sheets_meeting_sync as m
from skills.ceo._lib.sheets_meeting_sync import (
    AREAS,
    PROTO_HDR_RANGE,
    PROTO_HEADERS,
    TASK_HEADERS,
    TASKS_HDR_RANGE,
    TRIP_HEADERS,
    _as_list,
    _sanitize_cell,
    build_diary_row,
    build_meeting_row,
    build_protocol_row,
    build_task_rows,
    build_trip_row,
    classify_area,
    ensure_headers,
    parse_action_item,
    sync_capture,
    sync_diary_entry,
    sync_feedback,
    sync_focus,
    sync_meeting,
    sync_note,
    sync_trip,
)

NOTE = {
    "topic": "Переговоры с поставщиком",
    "date": "2026-06-24",
    "participants": ["Поставщик A", "CFO"],
    "summary": "Согласовали отсрочку.",
    "decisions": ["Берём отсрочку 30 дней"],
    "action_items": ["Поставщик A / до 27.06 — прислать прайс", "Подготовить договор"],
}
NID = "2026-06-24/1430-postavshchik.md"
NOW = "2026-06-24T15:10:00Z"


# --- classify_area ----------------------------------------------------------
def test_explicit_tag_wins():
    assert classify_area(None, "по Finance & Capital: обсудили cashflow") == "Finance & Capital"


def test_explicit_tag_normalized_whitespace():
    assert classify_area("Health", "по   finance & capital : ...") == "Finance & Capital"


def test_area_hint_used_when_valid():
    assert classify_area("Health", "разговор про сон") == "Health"


def test_invalid_hint_falls_back():
    assert classify_area("Маркетинг", "что-то непонятное") == "Не определено"


def test_empty_falls_back():
    assert classify_area(None, "ничего конкретного") == "Не определено"


def test_twelve_areas_present():
    assert "CEO / Tandem Group" in AREAS and len(AREAS) == 12


# --- parse_action_item ------------------------------------------------------
def test_parse_full():
    assert parse_action_item("Поставщик A / до 27.06 — прислать прайс") == (
        "Поставщик A", "до 27.06", "прислать прайс")


def test_parse_owner_only():
    assert parse_action_item("CFO — подготовить бюджет") == ("CFO", "", "подготовить бюджет")


def test_parse_plain():
    assert parse_action_item("Подготовить договор") == ("", "", "Подготовить договор")


# --- row builders -----------------------------------------------------------
def test_protocol_row_shape():
    row = build_protocol_row(NOTE, NID, "Finance & Capital", NOW)
    assert len(row) == 10
    assert row[0] == NID and row[1] == "2026-06-24" and row[2] == "14:30"
    assert row[3] == "Finance & Capital" and row[4] == "Переговоры с поставщиком"
    assert row[5] == "Поставщик A; CFO" and row[8] == "2" and row[9] == NOW


def test_task_rows():
    rows = build_task_rows(NOTE, NID, "Finance & Capital", NOW)
    assert len(rows) == 2
    assert rows[0][0] == NID + "#0" and rows[0][1] == NID
    assert rows[0][6] == "Поставщик A" and rows[0][7] == "до 27.06" and rows[0][8] == "open"
    assert rows[1][0] == NID + "#1" and rows[1][5] == "Подготовить договор"


# --- sync_note (idempotency, dry-run) --------------------------------------
class FakeGW:
    def __init__(self, existing_ids=None, headers_present=False):
        self.existing = existing_ids or []
        self.headers_present = headers_present
        self.appended = []  # list of (range, values)
        self.updated = []  # list of (range, values)
        self.tabs_ensured = []  # list of tab titles

    def ensure_tab(self, sheet_id, title):
        self.tabs_ensured.append(title)

    def get(self, sheet_id, rng):
        if "A1:" in rng:  # header row lookup (any tab)
            return [["hdr"]] if self.headers_present else []
        return [[i] for i in self.existing]

    def append(self, sheet_id, rng, values):
        self.appended.append((rng, values))

    def update(self, sheet_id, rng, values):
        self.updated.append((rng, values))


def test_first_write_appends_both_tabs():
    gw = FakeGW()
    res = sync_note(NOTE, "Health", "SID", gw, NOW, note_id=NID)
    assert res["protocol_written"] and res["tasks_written"] == 2 and not res["skipped"]
    ranges = [r for r, _ in gw.appended]
    assert any("Протоколы" in r for r in ranges)
    assert any("Задачи" in r for r in ranges)


def test_idempotent_skip_when_note_id_exists():
    gw = FakeGW(existing_ids=[NID])
    res = sync_note(NOTE, "Health", "SID", gw, NOW, note_id=NID)
    assert res["skipped"] and res["tasks_written"] == 0 and gw.appended == []


def test_sync_note_self_creates_tabs():
    gw = FakeGW()
    sync_note(NOTE, "Health", "SID", gw, NOW, note_id=NID)
    assert "Протоколы" in gw.tabs_ensured and "Задачи" in gw.tabs_ensured


def test_sync_diary_self_creates_tab():
    gw = FakeGW(headers_present=False)
    sync_diary_entry({"content": "x"}, "SID", gw, NOW)
    assert "Дневник" in gw.tabs_ensured


def test_dry_run_writes_nothing():
    gw = FakeGW()
    res = sync_note(NOTE, "Health", "SID", gw, NOW, note_id=NID, dry_run=True)
    assert gw.appended == [] and res["protocol_written"] is True


def test_explicit_tag_overrides_hint_in_sync():
    gw = FakeGW()
    note = dict(NOTE, summary="по Sport: тренировка")
    res = sync_note(note, "Health", "SID", gw, NOW, note_id=NID)
    assert res["area"] == "Sport"


# --- ensure_headers --------------------------------------------------------
def test_ensure_headers_writes_when_empty():
    gw = FakeGW(headers_present=False)
    written = ensure_headers(gw, "SID")
    assert len(gw.updated) == 2
    assert gw.updated[0] == (PROTO_HDR_RANGE, [PROTO_HEADERS])
    assert gw.updated[1] == (TASKS_HDR_RANGE, [TASK_HEADERS])
    assert written == {PROTO_HDR_RANGE: True, TASKS_HDR_RANGE: True}


def test_ensure_headers_idempotent_when_present():
    gw = FakeGW(headers_present=True)
    written = ensure_headers(gw, "SID")
    assert gw.updated == [] and written == {}


def test_sync_writes_headers_before_append():
    gw = FakeGW()  # empty sheet → headers absent
    sync_note(NOTE, "Health", "SID", gw, NOW, note_id=NID)
    assert len(gw.updated) == 2  # headers written for both tabs
    assert any("Протоколы" in r for r, _ in gw.appended)


# --- diary ------------------------------------------------------------------
def test_build_diary_row():
    row = build_diary_row(
        {"content": "устал", "energy": "6/10", "mood": "ок", "context": "работа"},
        "2026-06-28T10:00:00Z",
    )
    assert row == ["2026-06-28", "10:00", "устал", "6/10", "ок", "работа", "2026-06-28T10:00:00Z"]


def test_sync_diary_appends_with_headers():
    gw = FakeGW(headers_present=False)
    res = sync_diary_entry({"content": "тест"}, "SID", gw, "2026-06-28T10:00:00Z")
    assert res == {"diary_written": True}
    assert any("Дневник" in r for r, _ in gw.updated)  # header written
    assert any("Дневник" in r for r, _ in gw.appended)  # row appended


def test_sync_diary_dry_run_writes_nothing():
    gw = FakeGW()
    sync_diary_entry({"content": "x"}, "SID", gw, "2026-06-28T10:00:00Z", dry_run=True)
    assert gw.appended == [] and gw.updated == []


# --- trips -------------------------------------------------------------------
TRIP = {
    "destination": "Бухарест, Румыния",
    "start_date": "2026-07-10",
    "end_date": "2026-07-12",
    "purpose": "Переговоры по Pharma",
    "agenda": ["10.07 встреча с поставщиком A", "11.07 осмотр квартиры"],
    "action_items": ["Подготовить договор", "Забронировать отель"],
    "status": "planned",
}
TRIP_ID = "2026-06-28-buharest-rumyniya.md"


def test_build_trip_row_shape_and_days():
    row = build_trip_row(TRIP, TRIP_ID, "Pharma Project Romania", NOW)
    assert len(row) == len(TRIP_HEADERS) == 12
    assert row[0] == TRIP_ID and row[2] == "Pharma Project Romania"
    assert row[3] == "Бухарест, Румыния" and row[4] == "2026-07-10" and row[5] == "2026-07-12"
    assert row[6] == "3"  # inclusive day count
    assert row[8] == "10.07 встреча с поставщиком A; 11.07 осмотр квартиры"
    assert row[9] == "Подготовить договор; Забронировать отель"
    assert row[10] == "planned" and row[11] == NOW


def test_build_trip_row_no_dates_blank_days():
    row = build_trip_row({"destination": "Кишинёв"}, TRIP_ID, "Не определено", NOW)
    assert row[4] == "" and row[5] == "" and row[6] == ""
    assert row[10] == "planned"  # default status


def test_sync_trip_appends_with_headers():
    gw = FakeGW(headers_present=False)
    res = sync_trip(TRIP, "Pharma Project Romania", "SID", gw, NOW, trip_id=TRIP_ID)
    assert res["trip_written"] and not res["skipped"]
    assert "Поездки" in gw.tabs_ensured  # tab self-created
    assert any("Поездки" in r for r, _ in gw.updated)  # header written
    assert any("Поездки" in r for r, _ in gw.appended)  # row appended


def test_sync_trip_idempotent_skip():
    gw = FakeGW(existing_ids=[TRIP_ID])
    res = sync_trip(TRIP, None, "SID", gw, NOW, trip_id=TRIP_ID)
    assert res["skipped"] and not res["trip_written"] and gw.appended == []


def test_sync_trip_dry_run_writes_nothing():
    gw = FakeGW()
    sync_trip(TRIP, None, "SID", gw, NOW, trip_id=TRIP_ID, dry_run=True)
    assert gw.appended == [] and gw.updated == []


def test_main_trip_success(monkeypatch, capsys):
    monkeypatch.setenv("HERMES_MEETING_SHEET_ID", "SID")
    monkeypatch.setattr(m, "GoogleApiGW", lambda *a, **k: FakeGW())
    rc = m.main(["--trip", "--save", json.dumps(TRIP), "--note-id", TRIP_ID])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["trip_written"] and out["area"] == "Не определено"


# --- CLI / adapter ----------------------------------------------------------
def test_cli_requires_sheet_id(monkeypatch, capsys):
    monkeypatch.delenv("HERMES_MEETING_SHEET_ID", raising=False)
    rc = m.main(["--save", json.dumps({"topic": "t", "action_items": []}), "--note-id", "x"])
    assert rc == 2
    assert "HERMES_MEETING_SHEET_ID" in capsys.readouterr().err


def _patch_run(monkeypatch, stdout):
    def fake_run(cmd, capture_output, text, timeout):
        class R:
            returncode = 0
            stderr = ""
        R.stdout = stdout
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)


def test_gw_get_parses_bare_list(monkeypatch):
    # google_api `sheets get` prints a BARE values list — the real contract.
    _patch_run(monkeypatch, json.dumps([["id1"], ["id2"]]))
    gw = m.GoogleApiGW("/path/google_api.py")
    assert gw.get("SID", "Протоколы!A:A") == [["id1"], ["id2"]]


def test_gw_get_tolerates_values_dict(monkeypatch):
    # defensive: also accept {"values": [...]}
    _patch_run(monkeypatch, json.dumps({"values": [["id1"]]}))
    gw = m.GoogleApiGW("/path/google_api.py")
    assert gw.get("SID", "Протоколы!A:A") == [["id1"]]


def test_gw_get_empty(monkeypatch):
    _patch_run(monkeypatch, "[]")
    gw = m.GoogleApiGW("/path/google_api.py")
    assert gw.get("SID", "Протоколы!A:A") == []


# --- hardening: formula injection / non-list / bad-json -------------------
def test_sanitize_cell_neutralizes_formulas():
    assert _sanitize_cell('=IMPORTDATA("x")') == "'=IMPORTDATA(\"x\")"
    assert _sanitize_cell("+cmd") == "'+cmd"
    assert _sanitize_cell("@x") == "'@x"
    assert _sanitize_cell("-cmd") == "'-cmd"  # leading dash, non-numeric → escaped
    assert _sanitize_cell("-5") == "-5"        # negative number preserved
    assert _sanitize_cell("обычный текст") == "обычный текст"


def test_gw_append_sanitizes(monkeypatch):
    captured = {}

    def fake_run(self, *args):
        captured["args"] = args
        return ""
    monkeypatch.setattr(m.GoogleApiGW, "_run", fake_run)
    gw = m.GoogleApiGW("/p")
    gw.append("SID", "Задачи!A:J", [["=EVIL()", "ok"]])
    assert "'=EVIL()" in captured["args"][-1]  # formula escaped in the JSON values


def test_as_list_coerces_string():
    assert _as_list("CFO") == ["CFO"] and _as_list(None) == [] and _as_list(["a"]) == ["a"]


def test_protocol_row_string_participants_not_char_split():
    row = build_protocol_row(dict(NOTE, participants="CFO"), NID, "Health", NOW)
    assert row[5] == "CFO"  # NOT "C; F; O"


def test_main_bad_json_clean_exit(monkeypatch, capsys):
    monkeypatch.setenv("HERMES_MEETING_SHEET_ID", "SID")
    rc = m.main(["--capture", "--save", "{bad json", "--note-id", "x"])
    assert rc == 2 and "JSON" in capsys.readouterr().err


def test_gw_raises_on_nonzero(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        class R:
            returncode = 1
            stdout = ""
            stderr = "boom"
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        m.GoogleApiGW("/p").get("SID", "A:A")


def test_main_handles_sheets_failure_logs_and_warns(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HERMES_MEETING_SHEET_ID", "SID")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    def boom(*a, **k):
        raise RuntimeError("google_api failed: quota")
    monkeypatch.setattr(m, "sync_note", boom)

    rc = m.main(["--save", json.dumps(NOTE), "--note-id", NID])
    assert rc == 3
    out = json.loads(capsys.readouterr().out)
    assert out["note_saved"] is True and "Sheet" in out["warning"]
    log = tmp_path / "logs" / "errors.log"
    assert log.exists() and "sheets_meeting_sync" in log.read_text(encoding="utf-8")


def test_main_success(monkeypatch, capsys):
    monkeypatch.setenv("HERMES_MEETING_SHEET_ID", "SID")
    monkeypatch.setattr(m, "GoogleApiGW", lambda *a, **k: FakeGW())
    rc = m.main(["--save", json.dumps(NOTE), "--note-id", NID])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["protocol_written"] and out["tasks_written"] == 2


# --- capture (standalone task / decision / insight) -------------------------
CAP_ID = "cap/2026-06-29/070200-task"


def test_sync_capture_task_to_zadachi_tab():
    gw = FakeGW(headers_present=True)
    cap = {"type": "task", "context": "Бухарест", "content": "Купить лекарства"}
    res = sync_capture(cap, None, "SID", gw, NOW, capture_id=CAP_ID)
    assert res["capture_written"] and res["tab"] == "Задачи" and not res["skipped"]
    rng, vals = gw.appended[0]
    assert "Задачи" in rng
    assert vals[0][0] == CAP_ID and vals[0][4] == "Заметка"
    # free-form context folded into the task cell so it is not lost in the Sheet
    assert vals[0][5] == "Купить лекарства — Бухарест"


def test_sync_capture_task_no_context_keeps_plain_content():
    gw = FakeGW(headers_present=True)
    cap = {"type": "task", "context": "", "content": "Позвонить юристу"}
    sync_capture(cap, None, "SID", gw, NOW, capture_id="cap/x/9-task")
    assert gw.appended[0][1][0][5] == "Позвонить юристу"


def test_sync_capture_decision_to_resheniya_tab():
    gw = FakeGW(headers_present=True)
    cap = {"type": "decision", "context": "Pharma Project Romania", "content": "Берём отсрочку"}
    res = sync_capture(cap, None, "SID", gw, NOW, capture_id="cap/x/1-decision")
    assert res["tab"] == "Решения"
    assert any("Решения" in r for r, _ in gw.appended)
    assert "Решения" in gw.tabs_ensured


def test_sync_capture_insight_to_idei_tab():
    gw = FakeGW(headers_present=True)
    cap = {"type": "insight", "context": "", "content": "Рынок смещается в премиум"}
    res = sync_capture(cap, None, "SID", gw, NOW, capture_id="cap/x/1-insight")
    assert res["tab"] == "Идеи"
    assert any("Идеи" in r for r, _ in gw.appended)


def test_sync_capture_idempotent_skip():
    gw = FakeGW(existing_ids=[CAP_ID], headers_present=True)
    cap = {"type": "task", "context": "", "content": "дубль"}
    res = sync_capture(cap, None, "SID", gw, NOW, capture_id=CAP_ID)
    assert res["skipped"] and not res["capture_written"] and gw.appended == []


def test_sync_capture_writes_headers_when_absent():
    gw = FakeGW(headers_present=False)
    cap = {"type": "task", "context": "", "content": "новая задача"}
    sync_capture(cap, None, "SID", gw, NOW, capture_id="cap/x/2-task")
    assert gw.updated and any("Задачи" in r for r, _ in gw.updated)


def test_sync_capture_unknown_type_noop():
    gw = FakeGW(headers_present=True)
    cap = {"type": "meeting", "context": "", "content": "встреча"}
    res = sync_capture(cap, None, "SID", gw, NOW, capture_id="cap/x/3-meeting")
    assert not res["capture_written"] and gw.appended == []


def test_sync_capture_dry_run_writes_nothing():
    gw = FakeGW(headers_present=False)
    cap = {"type": "task", "context": "", "content": "dry"}
    res = sync_capture(cap, None, "SID", gw, NOW, capture_id="cap/x/4-task", dry_run=True)
    assert gw.appended == [] and gw.updated == [] and res["capture_written"]


def test_main_capture_success(monkeypatch, capsys):
    monkeypatch.setenv("HERMES_MEETING_SHEET_ID", "SID")
    monkeypatch.setattr(m, "GoogleApiGW", lambda *a, **k: FakeGW(headers_present=True))
    cap = {"type": "task", "context": "Бухарест", "content": "Купить лекарства"}
    rc = m.main(["--capture", "--save", json.dumps(cap), "--note-id", CAP_ID])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["capture_written"] and out["tab"] == "Задачи"


# --- feedback (/tune corrections) -------------------------------------------
FB_ID = "fb/2026-06-29/072000-rule"


def test_sync_feedback_appends_to_korrektirovki():
    gw = FakeGW(headers_present=True)
    res = sync_feedback({"kind": "правило", "text": "пиши короче"}, "SID", gw, NOW, feedback_id=FB_ID)
    assert res["feedback_written"] and not res["skipped"]
    rng, vals = gw.appended[0]
    assert "Корректировки" in rng
    assert vals[0][0] == FB_ID and vals[0][2] == "правило" and vals[0][4] == "applied"
    assert "Корректировки" in gw.tabs_ensured


def test_sync_feedback_bug_status_open():
    gw = FakeGW(headers_present=True)
    res = sync_feedback({"kind": "баг", "text": "нет кнопок"}, "SID", gw, NOW, feedback_id="fb/x/1-bug")
    assert res["feedback_written"]
    assert gw.appended[0][1][0][4] == "open"  # bug starts open


def test_sync_feedback_idempotent_skip():
    gw = FakeGW(existing_ids=[FB_ID], headers_present=True)
    res = sync_feedback({"kind": "правило", "text": "дубль"}, "SID", gw, NOW, feedback_id=FB_ID)
    assert res["skipped"] and not res["feedback_written"] and gw.appended == []


def test_main_feedback_success(monkeypatch, capsys):
    monkeypatch.setenv("HERMES_MEETING_SHEET_ID", "SID")
    monkeypatch.setattr(m, "GoogleApiGW", lambda *a, **k: FakeGW(headers_present=True))
    fb = {"kind": "правило", "text": "обращайся на ты"}
    rc = m.main(["--feedback", "--save", json.dumps(fb), "--note-id", FB_ID])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["feedback_written"]


# --- meetings (/prep agendas) -----------------------------------------------
MTG = {"date": "2026-06-30", "time": "10:00", "title": "Finance",
       "participants": ["CFO"], "agenda": ["Кэшфлоу?", "Отсрочка?"], "status": "planned"}
MTG_ID = "evt_abc123"


def test_sync_meeting_appends_new():
    gw = FakeGW(headers_present=True)  # empty id column → append
    res = sync_meeting(MTG, "SID", gw, NOW, meeting_id=MTG_ID)
    assert res["meeting_written"] and not res["updated"]
    rng, vals = gw.appended[0]
    assert "Встречи" in rng
    assert vals[0][0] == MTG_ID and vals[0][3] == "Finance"
    assert "1. Кэшфлоу?" in vals[0][5] and "2. Отсрочка?" in vals[0][5]  # numbered list


def test_sync_meeting_upserts_existing():
    gw = FakeGW(existing_ids=["meeting_id", MTG_ID], headers_present=True)  # header + 1 row
    res = sync_meeting(MTG, "SID", gw, NOW, meeting_id=MTG_ID)
    assert res["meeting_written"] and res["updated"] and res["row"] == 2
    assert any("Встречи!A2:G2" in r for r, _ in gw.updated)
    assert gw.appended == []  # updated in place, not duplicated


def test_build_meeting_row_string_agenda_passthrough():
    row = build_meeting_row({"title": "X", "agenda": "свободный текст"}, "id1")
    assert row[5] == "свободный текст" and row[0] == "id1"


def test_main_meeting_success(monkeypatch, capsys):
    monkeypatch.setenv("HERMES_MEETING_SHEET_ID", "SID")
    monkeypatch.setattr(m, "GoogleApiGW", lambda *a, **k: FakeGW(headers_present=True))
    rc = m.main(["--meeting", "--save", json.dumps(MTG), "--note-id", MTG_ID])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["meeting_written"]


# --- focus (/morning) -------------------------------------------------------
def test_sync_focus_appends_to_fokus():
    gw = FakeGW(headers_present=True)
    res = sync_focus({"text": "Я спокоен и собран"}, "SID", gw, NOW, focus_id="focus/x/1")
    assert res["focus_written"] and not res["skipped"]
    rng, vals = gw.appended[0]
    assert "Фокус" in rng and vals[0][0] == "focus/x/1" and vals[0][2] == "Я спокоен и собран"
    assert "Фокус" in gw.tabs_ensured


def test_sync_focus_idempotent():
    gw = FakeGW(existing_ids=["focus/x/1"], headers_present=True)
    res = sync_focus({"text": "dup"}, "SID", gw, NOW, focus_id="focus/x/1")
    assert res["skipped"] and gw.appended == []
