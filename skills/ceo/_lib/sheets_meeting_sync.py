#!/usr/bin/env python3
"""Meeting → Google Sheets sync for the /notes skill (CEO OS).

Takes the SAME structured JSON that /notes (and /diary protocol) already
produce and appends rows to ONE master Google Sheet with two tabs:

  Протоколы — one row per meeting
  Задачи    — one row per action item (seeds the future task tracker #4)

Both tabs carry a `направление` column (one of the 12 areas in memory/areas.md,
else "Не определено"). Idempotent by note_id / task_id — re-running never
duplicates rows.

Reuses, does not reimplement: extraction lives in /notes; the actual Sheets
write goes through skills/productivity/google-workspace/scripts/google_api.py
(scope `spreadsheets` already requested there).

Sheet ID comes from env HERMES_MEETING_SHEET_ID (not a secret, but prod config
is the CEO's; never hardcoded). Stdlib only — safe under cron python.

CLI:
  python sheets_meeting_sync.py --save '<JSON>' --note-id '<saved_path>' [--area X] [--dry-run]

Exit codes: 0 ok / 2 config missing (no sheet id) / 3 sheets write failed
(note .md is still saved upstream; caller warns the user but does not fail).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import subprocess
import sys

# --- areas (verbatim labels from memory/areas.md) ---------------------------
AREAS = [
    "CEO / Tandem Group", "Finance & Capital", "Health", "Супруга",
    "Parents", "Sport", "Learning", "Travel & Recovery",
    "Brasov Apartment", "Pharma Project Romania",
    "Personal Expertise", "Knowledge Capitalization",
]
UNKNOWN = "Не определено"

PROTO_TAB = "Протоколы"
TASKS_TAB = "Задачи"
PROTO_RANGE = f"{PROTO_TAB}!A:J"
TASKS_RANGE = f"{TASKS_TAB}!A:J"
ID_RANGE = f"{PROTO_TAB}!A:A"  # note_id column for idempotency
PROTO_HDR_RANGE = f"{PROTO_TAB}!A1:J1"
TASKS_HDR_RANGE = f"{TASKS_TAB}!A1:J1"

# Row 1 headers (single source of truth; column order matches build_*_row).
PROTO_HEADERS = [
    "note_id", "Дата", "Время", "Направление", "Встреча",
    "Участники", "Резюме", "Решения", "Кол-во задач", "Создано",
]
TASK_HEADERS = [
    "task_id", "note_id", "Дата", "Направление", "Встреча",
    "Задача", "Ответственный", "Срок", "Статус", "Создано",
]

DIARY_TAB = "Дневник"
DIARY_RANGE = f"{DIARY_TAB}!A:G"
DIARY_HDR_RANGE = f"{DIARY_TAB}!A1:G1"
DIARY_HEADERS = ["Дата", "Время", "Запись", "Энергия", "Настрой", "Контекст", "Создано"]

TRIPS_TAB = "Поездки"
TRIPS_RANGE = f"{TRIPS_TAB}!A:L"
TRIPS_HDR_RANGE = f"{TRIPS_TAB}!A1:L1"
TRIPS_ID_RANGE = f"{TRIPS_TAB}!A:A"  # trip_id column for idempotency
TRIP_HEADERS = [
    "trip_id", "Дата записи", "Направление", "Пункт назначения",
    "Начало", "Конец", "Дней", "Цель", "План / встречи", "Задачи", "Статус", "Создано",
]

# Standalone captures (/capture): a dictated/typed task, decision, or insight.
# Tasks reuse the meeting Задачи tab (one task list); decisions and insights get
# their own tabs so the CEO's whole context lives in his Sheet, not markdown.
DECISIONS_TAB = "Решения"
DECISIONS_RANGE = f"{DECISIONS_TAB}!A:J"
DECISIONS_HDR_RANGE = f"{DECISIONS_TAB}!A1:J1"
DECISIONS_ID_RANGE = f"{DECISIONS_TAB}!A:A"
DECISION_HEADERS = [
    "decision_id", "Дата", "Направление", "Контекст", "Решение",
    "Причина", "Ожидаемый результат", "Дата ревью", "Статус", "Создано",
]

IDEAS_TAB = "Идеи"
IDEAS_RANGE = f"{IDEAS_TAB}!A:F"
IDEAS_HDR_RANGE = f"{IDEAS_TAB}!A1:F1"
IDEAS_ID_RANGE = f"{IDEAS_TAB}!A:A"
IDEA_HEADERS = ["idea_id", "Дата", "Направление", "Контекст", "Идея", "Создано"]

CAPTURE_TASKS_ID_RANGE = f"{TASKS_TAB}!A:A"  # capture tasks dedupe by task_id in Задачи

# Meeting agendas (/prep): one row per meeting/day with the question checklist the
# CEO focuses on. UPSERT by meeting_id (regenerating an agenda updates the row, not
# duplicates). The CEO can edit the Повестка cell directly in Sheets.
MEETINGS_TAB = "Встречи"
MEETINGS_RANGE = f"{MEETINGS_TAB}!A:G"
MEETINGS_HDR_RANGE = f"{MEETINGS_TAB}!A1:G1"
MEETINGS_ID_RANGE = f"{MEETINGS_TAB}!A:A"
MEETING_HEADERS = ["meeting_id", "Дата", "Время", "Название", "Участники", "Повестка", "Статус"]

# Feedback / corrections (/tune): self-tune rules + dev bug reports, for audit.
FEEDBACK_TAB = "Корректировки"
FEEDBACK_RANGE = f"{FEEDBACK_TAB}!A:F"
FEEDBACK_HDR_RANGE = f"{FEEDBACK_TAB}!A1:F1"
FEEDBACK_ID_RANGE = f"{FEEDBACK_TAB}!A:A"
FEEDBACK_HEADERS = ["feedback_id", "Дата", "Тип", "Текст", "Статус", "Создано"]

GOOGLE_API = os.environ.get(
    "HERMES_GOOGLE_API",
    "/opt/hermes/skills/productivity/google-workspace/scripts/google_api.py",
)


def _norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _as_list(v: object) -> list:
    """Coerce a field to a list. A bare string would otherwise be iterated by
    CHARACTER (e.g. "CFO" → ["C","F","O"]) when joined into a cell."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [str(v)]


def _sanitize_cell(v: object) -> str:
    """Neutralize spreadsheet formula injection: a cell starting with = + @ (or a
    non-numeric -) is interpreted as a formula under USER_ENTERED. Prefix ' so
    user/LLM-supplied content like '=IMPORTDATA(...)' lands as literal text."""
    s = str(v)
    if s and (s[0] in ("=", "+", "@") or (s[0] == "-" and not s[1:2].isdigit())):
        return "'" + s
    return s


def classify_area(area_hint: str | None, text: str) -> str:
    """Explicit tag `по <area>:` / `#<area>` wins, else valid LLM hint, else fallback."""
    ntext = _norm(text)
    for a in AREAS:
        na = _norm(a)
        if f"по {na}" in ntext or f"#{na}" in ntext:
            return a
    if area_hint:
        nh = _norm(area_hint)
        for a in AREAS:
            if _norm(a) == nh:
                return a
    return UNKNOWN


def _time_from_note_id(note_id: str) -> str:
    m = re.search(r"/(\d{2})(\d{2})-", note_id or "")
    return f"{m.group(1)}:{m.group(2)}" if m else ""


def parse_action_item(s: str) -> tuple[str, str, str]:
    """Parse `owner / due — описание` → (owner, due, task). Missing parts → ""."""
    s = (s or "").strip()
    owner, due, task = "", "", s
    if "—" in s:
        left, task = s.split("—", 1)
        task = task.strip()
        if "/" in left:
            owner, due = [p.strip() for p in left.split("/", 1)]
        else:
            owner = left.strip()
    return owner, due, task


def build_protocol_row(note: dict, note_id: str, area: str, now_iso: str) -> list[str]:
    ai = _as_list(note.get("action_items"))
    decisions = _as_list(note.get("decisions"))
    return [
        note_id,
        note.get("date", ""),
        _time_from_note_id(note_id),
        area,
        note.get("topic", ""),
        "; ".join(str(p) for p in _as_list(note.get("participants"))),
        note.get("summary", ""),
        " ".join(f"{i + 1}) {d}" for i, d in enumerate(decisions)),
        str(len(ai)),
        now_iso,
    ]


def build_task_rows(note: dict, note_id: str, area: str, now_iso: str) -> list[list[str]]:
    rows = []
    for i, item in enumerate(_as_list(note.get("action_items"))):
        owner, due, task = parse_action_item(item)
        rows.append([
            f"{note_id}#{i}", note_id, note.get("date", ""), area,
            note.get("topic", ""), task, owner, due, "open", now_iso,
        ])
    return rows


class GoogleApiGW:
    """Thin adapter over google_api.py (separate process with its own deps)."""

    def __init__(self, script: str = GOOGLE_API):
        self.script = script

    def _run(self, *args: str) -> str:
        r = subprocess.run(
            [sys.executable, self.script, *args],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            raise RuntimeError(f"google_api failed: {r.stderr.strip()[:2000]}")
        return r.stdout

    def get(self, sheet_id: str, rng: str) -> list[list[str]]:
        out = self._run("sheets", "get", sheet_id, rng)
        if not out.strip():
            return []
        data = json.loads(out)
        # google_api `sheets get` prints a BARE values list (result.get("values", []));
        # tolerate a {"values": [...]} dict too. Calling .get() on the bare list was
        # a crash ("'list' object has no attribute 'get'") on any non-empty range.
        if isinstance(data, dict):
            return data.get("values", [])
        return data if isinstance(data, list) else []

    def append(self, sheet_id: str, rng: str, values: list[list[str]]) -> None:
        safe = [[_sanitize_cell(c) for c in row] for row in values]
        self._run("sheets", "append", sheet_id, rng,
                  "--values", json.dumps(safe, ensure_ascii=False))

    def update(self, sheet_id: str, rng: str, values: list[list[str]]) -> None:
        safe = [[_sanitize_cell(c) for c in row] for row in values]
        self._run("sheets", "update", sheet_id, rng,
                  "--values", json.dumps(safe, ensure_ascii=False))

    def ensure_tab(self, sheet_id: str, title: str) -> None:
        self._run("sheets", "ensure-tab", sheet_id, title)


def ensure_headers(gw, sheet_id: str) -> dict:
    """Write row-1 headers to each tab if missing. Idempotent (no-op if present)."""
    written = {}
    for hdr_range, headers in ((PROTO_HDR_RANGE, PROTO_HEADERS), (TASKS_HDR_RANGE, TASK_HEADERS)):
        existing = gw.get(sheet_id, hdr_range)
        first = existing[0] if existing else []
        if not first or not any(str(c).strip() for c in first):
            gw.update(sheet_id, hdr_range, [headers])
            written[hdr_range] = True
    return written


def ensure_diary_headers(gw, sheet_id: str) -> bool:
    """Write Дневник row-1 headers if missing. Idempotent."""
    existing = gw.get(sheet_id, DIARY_HDR_RANGE)
    first = existing[0] if existing else []
    if not first or not any(str(c).strip() for c in first):
        gw.update(sheet_id, DIARY_HDR_RANGE, [DIARY_HEADERS])
        return True
    return False


def build_diary_row(entry: dict, now_iso: str) -> list[str]:
    return [
        now_iso[:10], now_iso[11:16],
        str(entry.get("content", "")), str(entry.get("energy", "")),
        str(entry.get("mood", "")), str(entry.get("context", "")), now_iso,
    ]


def sync_diary_entry(entry: dict, sheet_id: str, gw, now_iso: str, *, dry_run: bool = False) -> dict:
    """Append a diary entry to the Дневник tab (append-only, for later analytics)."""
    row = build_diary_row(entry, now_iso)
    if not dry_run:
        gw.ensure_tab(sheet_id, DIARY_TAB)  # self-create (parity with other syncs)
        ensure_diary_headers(gw, sheet_id)
        gw.append(sheet_id, DIARY_RANGE, [row])
    return {"diary_written": True}


def _trip_days(start: str, end: str) -> str:
    """Inclusive day count between two ISO dates; "" if either is missing/invalid."""
    try:
        s = _dt.date.fromisoformat((start or "")[:10])
        e = _dt.date.fromisoformat((end or "")[:10])
    except ValueError:
        return ""
    d = (e - s).days + 1
    return str(d) if d > 0 else ""


def build_trip_row(trip: dict, trip_id: str, area: str, now_iso: str) -> list[str]:
    start = str(trip.get("start_date", "") or "")
    end = str(trip.get("end_date", "") or "")
    agenda = _as_list(trip.get("agenda"))
    actions = _as_list(trip.get("action_items"))
    return [
        trip_id,
        now_iso[:10],
        area,
        str(trip.get("destination", "") or ""),
        start,
        end,
        _trip_days(start, end),
        str(trip.get("purpose", "") or ""),
        "; ".join(str(x) for x in agenda),
        "; ".join(str(x) for x in actions),
        str(trip.get("status", "") or "planned"),
        now_iso,
    ]


def ensure_trip_headers(gw, sheet_id: str) -> bool:
    """Write Поездки row-1 headers if missing. Idempotent."""
    existing = gw.get(sheet_id, TRIPS_HDR_RANGE)
    first = existing[0] if existing else []
    if not first or not any(str(c).strip() for c in first):
        gw.update(sheet_id, TRIPS_HDR_RANGE, [TRIP_HEADERS])
        return True
    return False


def sync_trip(trip: dict, area_hint: str | None, sheet_id: str, gw,
              now_iso: str, *, trip_id: str, dry_run: bool = False) -> dict:
    """Idempotent: skip if trip_id already in Поездки!A:A. Returns a summary."""
    text = " ".join([str(trip.get("purpose", "") or ""), str(trip.get("destination", "") or "")])
    area = classify_area(area_hint, text)
    # Self-create the Поездки tab on first use (the master Sheet ships without it).
    if not dry_run:
        gw.ensure_tab(sheet_id, TRIPS_TAB)
    existing = {row[0] for row in gw.get(sheet_id, TRIPS_ID_RANGE) if row}
    if trip_id in existing:
        return {"trip_written": False, "skipped": True, "area": area}
    row = build_trip_row(trip, trip_id, area, now_iso)
    if not dry_run:
        ensure_trip_headers(gw, sheet_id)
        gw.append(sheet_id, TRIPS_RANGE, [row])
    return {"trip_written": True, "skipped": False, "area": area}


def _ensure_hdr(gw, sheet_id: str, hdr_range: str, headers: list[str]) -> bool:
    """Write row-1 headers to one tab if missing. Idempotent."""
    existing = gw.get(sheet_id, hdr_range)
    first = existing[0] if existing else []
    if not first or not any(str(c).strip() for c in first):
        gw.update(sheet_id, hdr_range, [headers])
        return True
    return False


def build_capture_task_row(cap: dict, capture_id: str, area: str, now_iso: str) -> list[str]:
    # Reuse Задачи schema: task_id, note_id, Дата, Направление, Встреча, Задача,
    # Ответственный, Срок, Статус, Создано. "Заметка" marks a standalone capture.
    # Free-form context (e.g. "Бухарест") that isn't one of the 12 areas would be
    # lost otherwise — fold it into the task cell so it survives in the Sheet.
    content = str(cap.get("content", ""))
    ctx = str(cap.get("context", "")).strip()
    task_cell = f"{content} — {ctx}" if ctx and ctx not in content else content
    return [
        capture_id, "", now_iso[:10], area, "Заметка",
        task_cell, "", "", "open", now_iso,
    ]


def build_capture_decision_row(cap: dict, capture_id: str, area: str, now_iso: str) -> list[str]:
    return [
        capture_id, now_iso[:10], area, str(cap.get("context", "")),
        str(cap.get("content", "")), "(уточнить)", "(уточнить)", "", "pending", now_iso,
    ]


def build_capture_idea_row(cap: dict, capture_id: str, area: str, now_iso: str) -> list[str]:
    return [
        capture_id, now_iso[:10], area, str(cap.get("context", "")),
        str(cap.get("content", "")), now_iso,
    ]


# type → (tab, append-range, id-range, header-range, headers, row-builder)
_CAPTURE_ROUTES = {
    "task": (TASKS_TAB, TASKS_RANGE, CAPTURE_TASKS_ID_RANGE, TASKS_HDR_RANGE,
             TASK_HEADERS, build_capture_task_row),
    "decision": (DECISIONS_TAB, DECISIONS_RANGE, DECISIONS_ID_RANGE, DECISIONS_HDR_RANGE,
                 DECISION_HEADERS, build_capture_decision_row),
    "insight": (IDEAS_TAB, IDEAS_RANGE, IDEAS_ID_RANGE, IDEAS_HDR_RANGE,
                IDEA_HEADERS, build_capture_idea_row),
}


def sync_capture(cap: dict, area_hint: str | None, sheet_id: str, gw,
                 now_iso: str, *, capture_id: str, dry_run: bool = False) -> dict:
    """Route a standalone capture (task/decision/insight) to its tab.

    Idempotent by capture_id in the tab's column A. meeting/recap are no-ops here
    (they belong to /notes and /diary). Self-creates the tab on first use.
    """
    ctype = (cap.get("type") or "").lower().strip()
    route = _CAPTURE_ROUTES.get(ctype)
    text = " ".join([str(cap.get("content", "")), str(cap.get("context", ""))])
    area = classify_area(area_hint, text)
    if route is None:
        return {"capture_written": False, "reason": f"type-not-synced:{ctype}", "area": area}
    tab, rng, id_range, hdr_range, headers, build_row = route
    if not dry_run:
        gw.ensure_tab(sheet_id, tab)
    existing = {r[0] for r in gw.get(sheet_id, id_range) if r}
    if capture_id in existing:
        return {"capture_written": False, "skipped": True, "tab": tab, "area": area}
    row = build_row(cap, capture_id, area, now_iso)
    if not dry_run:
        _ensure_hdr(gw, sheet_id, hdr_range, headers)
        gw.append(sheet_id, rng, [row])
    return {"capture_written": True, "skipped": False, "tab": tab, "area": area}


def build_meeting_row(mtg: dict, meeting_id: str) -> list[str]:
    parts = mtg.get("participants")
    parts_cell = "; ".join(str(p) for p in parts) if isinstance(parts, list) else str(parts or "")
    agenda = mtg.get("agenda")
    if isinstance(agenda, list):
        agenda_cell = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(agenda))
    else:
        agenda_cell = str(agenda or "")
    return [
        meeting_id,
        str(mtg.get("date", "")),
        str(mtg.get("time", "")),
        str(mtg.get("title", "")),
        parts_cell,
        agenda_cell,
        str(mtg.get("status", "") or "planned"),
    ]


def sync_meeting(mtg: dict, sheet_id: str, gw, now_iso: str,
                 *, meeting_id: str, dry_run: bool = False) -> dict:
    """Upsert a meeting agenda into the Встречи tab. Updates the row if meeting_id
    already exists (re-prep overwrites), else appends. Self-creates the tab."""
    if not dry_run:
        gw.ensure_tab(sheet_id, MEETINGS_TAB)
        _ensure_hdr(gw, sheet_id, MEETINGS_HDR_RANGE, MEETING_HEADERS)
    row = build_meeting_row(mtg, meeting_id)
    ids = [r[0] if r else "" for r in gw.get(sheet_id, MEETINGS_ID_RANGE)]
    if meeting_id in ids:
        idx = ids.index(meeting_id) + 1  # col A includes header at row 1
        if not dry_run:
            gw.update(sheet_id, f"{MEETINGS_TAB}!A{idx}:G{idx}", [row])
        return {"meeting_written": True, "updated": True, "row": idx}
    if not dry_run:
        gw.append(sheet_id, MEETINGS_RANGE, [row])
    return {"meeting_written": True, "updated": False}


def build_feedback_row(fb: dict, feedback_id: str, now_iso: str) -> list[str]:
    kind = str(fb.get("kind", "")) or "правило"
    status = "open" if kind == "баг" else "applied"
    return [feedback_id, now_iso[:10], kind, str(fb.get("text", "")), status, now_iso]


def sync_feedback(fb: dict, sheet_id: str, gw, now_iso: str,
                  *, feedback_id: str, dry_run: bool = False) -> dict:
    """Append a /tune entry (rule or bug) to the Корректировки tab. Idempotent by id."""
    if not dry_run:
        gw.ensure_tab(sheet_id, FEEDBACK_TAB)
    existing = {r[0] for r in gw.get(sheet_id, FEEDBACK_ID_RANGE) if r}
    if feedback_id in existing:
        return {"feedback_written": False, "skipped": True}
    row = build_feedback_row(fb, feedback_id, now_iso)
    if not dry_run:
        _ensure_hdr(gw, sheet_id, FEEDBACK_HDR_RANGE, FEEDBACK_HEADERS)
        gw.append(sheet_id, FEEDBACK_RANGE, [row])
    return {"feedback_written": True, "skipped": False}


def sync_note(note: dict, area_hint: str | None, sheet_id: str, gw,
              now_iso: str, *, note_id: str, dry_run: bool = False) -> dict:
    """Idempotent: skip if note_id already in Протоколы!A:A. Returns a summary."""
    text = " ".join([note.get("summary", ""), note.get("raw_text", "")])
    area = classify_area(area_hint, text)
    if not dry_run:  # self-create tabs (parity with sync_capture/trip/meeting)
        gw.ensure_tab(sheet_id, PROTO_TAB)
        gw.ensure_tab(sheet_id, TASKS_TAB)
    existing = {row[0] for row in gw.get(sheet_id, ID_RANGE) if row}
    if note_id in existing:
        return {"protocol_written": False, "tasks_written": 0, "skipped": True, "area": area}
    proto = build_protocol_row(note, note_id, area, now_iso)
    tasks = build_task_rows(note, note_id, area, now_iso)
    if not dry_run:
        ensure_headers(gw, sheet_id)
        gw.append(sheet_id, PROTO_RANGE, [proto])
        if tasks:
            gw.append(sheet_id, TASKS_RANGE, tasks)
    return {"protocol_written": True, "tasks_written": len(tasks), "skipped": False, "area": area}


def _errors_log_path() -> pathlib.Path:
    home = os.environ.get("HERMES_HOME") or str(pathlib.Path.home() / ".hermes")
    return pathlib.Path(home) / "logs" / "errors.log"


def log_sync_error(message: str) -> None:
    """Best-effort append to errors.log (never raises)."""
    try:
        p = _errors_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts} [sheets_meeting_sync] {message}\n")
    except Exception:
        pass


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save")
    ap.add_argument("--area", default=None)
    ap.add_argument("--note-id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="Run a built-in test note end-to-end with full traceback (diagnostics)")
    ap.add_argument("--diary", action="store_true",
                    help="Treat --save payload as a diary entry → Дневник tab")
    ap.add_argument("--trip", action="store_true",
                    help="Treat --save payload as a trip plan → Поездки tab")
    ap.add_argument("--capture", action="store_true",
                    help="Treat --save payload as a standalone capture "
                         "(task→Задачи / decision→Решения / insight→Идеи)")
    ap.add_argument("--feedback", action="store_true",
                    help="Treat --save payload as a /tune feedback entry → Корректировки tab")
    ap.add_argument("--meeting", action="store_true",
                    help="Treat --save payload as a meeting agenda (upsert) → Встречи tab")
    a = ap.parse_args(argv)

    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        sys.stderr.write(
            "HERMES_MEETING_SHEET_ID is not set — CEO must create the Sheet and set the env var.\n"
        )
        return 2

    # Parse --save ONCE, with a controlled error (not a raw traceback) on bad JSON.
    parsed = None
    if a.save:
        try:
            parsed = json.loads(a.save)
        except json.JSONDecodeError as exc:
            sys.stderr.write(f"--save expects valid JSON ({exc})\n")
            return 2

    if a.selftest:
        import traceback as _tb
        note = {
            "topic": "SELFTEST встреча", "date": _now_iso()[:10], "participants": ["Тест"],
            "summary": "по Finance: selftest", "decisions": ["решение 1"],
            "action_items": ["Тест / до пятницы — задача"],
        }
        try:
            res = sync_note(note, None, sheet_id, GoogleApiGW(), _now_iso(),
                            note_id="__selftest__/0000-selftest.md", dry_run=a.dry_run)
            print(json.dumps(res, ensure_ascii=False))
            return 0
        except Exception:
            _tb.print_exc()
            return 3

    if a.diary:
        entry = parsed or {}
        try:
            res = sync_diary_entry(entry, sheet_id, GoogleApiGW(), _now_iso(), dry_run=a.dry_run)
            print(json.dumps(res, ensure_ascii=False))
            return 0
        except Exception as exc:
            log_sync_error(f"diary: {exc}")
            print(json.dumps({"sheets_error": str(exc)[:200], "note_saved": True,
                              "warning": "⚠️ запись дневника сохранена, но не в Sheet"},
                             ensure_ascii=False))
            return 3

    if a.trip:
        if not a.save or not a.note_id:
            sys.stderr.write("--save and --note-id are required for --trip\n")
            return 2
        trip = parsed
        try:
            res = sync_trip(trip, a.area, sheet_id, GoogleApiGW(), _now_iso(),
                            trip_id=a.note_id, dry_run=a.dry_run)
            print(json.dumps(res, ensure_ascii=False))
            return 0
        except Exception as exc:
            log_sync_error(f"trip note_id={a.note_id}: {exc}")
            print(json.dumps({"sheets_error": str(exc)[:200], "note_saved": True,
                              "warning": "⚠️ поездка сохранена, но не записана в Sheet"},
                             ensure_ascii=False))
            return 3

    if a.capture:
        if not a.save or not a.note_id:
            sys.stderr.write("--save and --note-id are required for --capture\n")
            return 2
        cap = parsed
        try:
            res = sync_capture(cap, a.area, sheet_id, GoogleApiGW(), _now_iso(),
                               capture_id=a.note_id, dry_run=a.dry_run)
            print(json.dumps(res, ensure_ascii=False))
            return 0
        except Exception as exc:
            log_sync_error(f"capture id={a.note_id}: {exc}")
            print(json.dumps({"sheets_error": str(exc)[:200], "note_saved": True,
                              "warning": "⚠️ заметка сохранена, но не записана в Sheet"},
                             ensure_ascii=False))
            return 3

    if a.feedback:
        if not a.save or not a.note_id:
            sys.stderr.write("--save and --note-id are required for --feedback\n")
            return 2
        fb = parsed
        try:
            res = sync_feedback(fb, sheet_id, GoogleApiGW(), _now_iso(),
                                feedback_id=a.note_id, dry_run=a.dry_run)
            print(json.dumps(res, ensure_ascii=False))
            return 0
        except Exception as exc:
            log_sync_error(f"feedback id={a.note_id}: {exc}")
            print(json.dumps({"sheets_error": str(exc)[:200], "note_saved": True,
                              "warning": "⚠️ корректировка записана локально, но не в Sheet"},
                             ensure_ascii=False))
            return 3

    if a.meeting:
        if not a.save or not a.note_id:
            sys.stderr.write("--save and --note-id are required for --meeting\n")
            return 2
        mtg = parsed
        try:
            res = sync_meeting(mtg, sheet_id, GoogleApiGW(), _now_iso(),
                               meeting_id=a.note_id, dry_run=a.dry_run)
            print(json.dumps(res, ensure_ascii=False))
            return 0
        except Exception as exc:
            log_sync_error(f"meeting id={a.note_id}: {exc}")
            print(json.dumps({"sheets_error": str(exc)[:200], "note_saved": True,
                              "warning": "⚠️ повестка не записана в Sheet"},
                             ensure_ascii=False))
            return 3

    if not a.save or not a.note_id:
        sys.stderr.write("--save and --note-id are required (or use --selftest)\n")
        return 2

    note = parsed
    try:
        res = sync_note(note, a.area, sheet_id, GoogleApiGW(), _now_iso(),
                        note_id=a.note_id, dry_run=a.dry_run)
    except Exception as exc:  # sheets write failed — note .md is already saved upstream
        log_sync_error(f"note_id={a.note_id}: {exc}")
        print(json.dumps(
            {"sheets_error": str(exc)[:200], "note_saved": True,
             "warning": "⚠️ заметка сохранена, но не записана в Sheet"},
            ensure_ascii=False,
        ))
        return 3

    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
