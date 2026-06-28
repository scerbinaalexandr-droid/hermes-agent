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

GOOGLE_API = os.environ.get(
    "HERMES_GOOGLE_API",
    "/opt/hermes/skills/productivity/google-workspace/scripts/google_api.py",
)


def _norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


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
    ai = note.get("action_items") or []
    decisions = note.get("decisions") or []
    return [
        note_id,
        note.get("date", ""),
        _time_from_note_id(note_id),
        area,
        note.get("topic", ""),
        "; ".join(note.get("participants") or []),
        note.get("summary", ""),
        " ".join(f"{i + 1}) {d}" for i, d in enumerate(decisions)),
        str(len(ai)),
        now_iso,
    ]


def build_task_rows(note: dict, note_id: str, area: str, now_iso: str) -> list[list[str]]:
    rows = []
    for i, item in enumerate(note.get("action_items") or []):
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
        return (json.loads(out) or {}).get("values", []) if out.strip() else []

    def append(self, sheet_id: str, rng: str, values: list[list[str]]) -> None:
        self._run("sheets", "append", sheet_id, rng,
                  "--values", json.dumps(values, ensure_ascii=False))

    def update(self, sheet_id: str, rng: str, values: list[list[str]]) -> None:
        self._run("sheets", "update", sheet_id, rng,
                  "--values", json.dumps(values, ensure_ascii=False))


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


def sync_note(note: dict, area_hint: str | None, sheet_id: str, gw,
              now_iso: str, *, note_id: str, dry_run: bool = False) -> dict:
    """Idempotent: skip if note_id already in Протоколы!A:A. Returns a summary."""
    text = " ".join([note.get("summary", ""), note.get("raw_text", "")])
    area = classify_area(area_hint, text)
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
    a = ap.parse_args(argv)

    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        sys.stderr.write(
            "HERMES_MEETING_SHEET_ID is not set — CEO must create the Sheet and set the env var.\n"
        )
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

    if not a.save or not a.note_id:
        sys.stderr.write("--save and --note-id are required (or use --selftest)\n")
        return 2

    note = json.loads(a.save)
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
