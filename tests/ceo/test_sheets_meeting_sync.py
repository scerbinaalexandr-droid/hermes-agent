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
    build_protocol_row,
    build_task_rows,
    classify_area,
    ensure_headers,
    parse_action_item,
    sync_note,
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

    def get(self, sheet_id, rng):
        if "A1:J1" in rng:  # header row lookup
            return [["note_id"]] if self.headers_present else []
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


# --- CLI / adapter ----------------------------------------------------------
def test_cli_requires_sheet_id(monkeypatch, capsys):
    monkeypatch.delenv("HERMES_MEETING_SHEET_ID", raising=False)
    rc = m.main(["--save", json.dumps({"topic": "t", "action_items": []}), "--note-id", "x"])
    assert rc == 2
    assert "HERMES_MEETING_SHEET_ID" in capsys.readouterr().err


def test_gw_get_parses_subprocess(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        class R:
            returncode = 0
            stdout = json.dumps({"values": [["id1"], ["id2"]]})
            stderr = ""
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    gw = m.GoogleApiGW("/path/google_api.py")
    assert gw.get("SID", "Протоколы!A:A") == [["id1"], ["id2"]]


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
