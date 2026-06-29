"""Open-tasks helper — read the Задачи tab, surface what's open by deadline.

Closes the loop: capture/meeting action items land in Задачи (task_id, note_id,
Дата, Направление, Встреча, Задача, Ответственный, Срок, Статус, Создано); this
helper reads them back, drops done/closed, and buckets the rest by deadline so the
CEO sees what's overdue / due-soon every morning.

  --list : JSON {today, total_open, overdue[], soon[], later[]} for the LLM to format.

Best-effort: never raises hard; a missing sheet / unparseable deadline degrades.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import sys

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Chisinau")
except Exception:  # pragma: no cover
    _TZ = _dt.timezone(_dt.timedelta(hours=3))

_DONE = {"done", "closed", "выполнено", "выполнена", "готово", "cancelled",
         "отменено", "отменена", "complete", "completed", "x", "✓"}
_SOON_DAYS = 7


def _today() -> _dt.date:
    return _dt.datetime.now(_TZ).date()


def _parse_due(s: str, today: _dt.date) -> "_dt.date | None":
    """Parse a deadline cell into a date. Handles ISO, dd.mm.yyyy, dd.mm (current
    year, rolling to next year if it already passed long ago). Returns None on
    free-form text like 'до пятницы'."""
    s = (s or "").strip().lower().replace("до ", "").strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b", s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        yr = m.group(3)
        try:
            if yr:
                year = int(yr) + (2000 if len(yr) == 2 else 0)
                return _dt.date(year, mo, d)
            # bare dd.mm → current year. If already past, it surfaces as overdue
            # (never silently rolled forward, which could hide a real overdue task).
            return _dt.date(today.year, mo, d)
        except ValueError:
            return None
    return None


def _google_api() -> str:
    p = os.environ.get("HERMES_GOOGLE_API",
                       "/opt/hermes/skills/productivity/google-workspace/scripts/google_api.py")
    if not os.path.exists(p):
        p = str(_REPO / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py")
    return p


def cmd_list() -> dict:
    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        return {"ok": False, "reason": "no-sheet-configured"}
    try:
        from skills.ceo._lib.sheets_meeting_sync import GoogleApiGW, TASKS_TAB
    except Exception as exc:
        return {"ok": False, "reason": f"import:{exc}"}
    try:
        rows = GoogleApiGW(_google_api()).get(sheet_id, f"{TASKS_TAB}!A:J")
    except Exception as exc:
        return {"ok": False, "reason": f"read:{str(exc)[:200]}"}

    today = _today()
    overdue, soon, later = [], [], []
    for r in rows[1:]:  # skip header
        if not r or len(r) < 6:
            continue
        status = (r[8] if len(r) > 8 else "").strip().lower()
        if status in _DONE:
            continue
        task = (r[5] if len(r) > 5 else "").strip()
        if not task:
            continue
        due_raw = (r[7] if len(r) > 7 else "").strip()
        item = {
            "task": task,
            "area": (r[3] if len(r) > 3 else "").strip(),
            "owner": (r[6] if len(r) > 6 else "").strip(),
            "due": due_raw,
            "source": (r[4] if len(r) > 4 else "").strip(),
        }
        due = _parse_due(due_raw, today)
        if due and due < today:
            item["overdue_days"] = (today - due).days
            overdue.append((due, item))
        elif due and due <= today + _dt.timedelta(days=_SOON_DAYS):
            soon.append((due, item))
        else:
            later.append(item)

    overdue.sort(key=lambda x: x[0])
    soon.sort(key=lambda x: x[0])
    out_overdue = [i for _, i in overdue]
    out_soon = [i for _, i in soon]
    return {
        "ok": True,
        "today": today.isoformat(),
        "total_open": len(out_overdue) + len(out_soon) + len(later),
        "overdue": out_overdue,
        "soon": out_soon,
        "later": later,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true")
    ap.parse_args()
    json.dump(cmd_list(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
