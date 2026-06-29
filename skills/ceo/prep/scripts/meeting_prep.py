"""Meeting-prep helper — gather today's meetings + context; save agendas to Встречи.

The LLM does the reasoning (turning context into a focused question checklist per
meeting); this helper only does the deterministic I/O:

  --gather : today's Google Calendar events (EEST) + memory context
             (projects / active priorities / risks) as JSON.
  --save   : JSON {"meetings":[{meeting_id,date,time,title,participants,agenda[],status}]}
             → upsert each into the Встречи tab (best-effort, never raises hard).

Usage:
  python meeting_prep.py --gather
  python meeting_prep.py --save '{"meetings":[...]}'
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import subprocess
import sys

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

# EEST (Chisinau summer) — matches the "CEO Brief 07:30 EEST" cron convention.
TZ = _dt.timezone(_dt.timedelta(hours=3))


def _today_bounds() -> tuple[str, str, str]:
    now = _dt.datetime.now(TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return now.date().isoformat(), start.isoformat(), end.isoformat()


def _google_api() -> str:
    p = os.environ.get("HERMES_GOOGLE_API",
                       "/opt/hermes/skills/productivity/google-workspace/scripts/google_api.py")
    if not os.path.exists(p):
        p = str(_REPO / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py")
    return p


def _calendar_today() -> object:
    _, start, end = _today_bounds()
    try:
        r = subprocess.run(
            [sys.executable, _google_api(), "calendar", "list",
             "--start", start, "--end", end, "--max", "25"],
            capture_output=True, text=True, timeout=90,
        )
        if r.returncode == 0:
            return json.loads((r.stdout or "[]").strip() or "[]")
        return {"error": ((r.stdout or "") + (r.stderr or "")).strip()[:300]}
    except Exception as exc:
        return {"error": str(exc)[:300]}


def cmd_gather() -> dict:
    date, _, _ = _today_bounds()
    out: dict = {"today": date, "tz": "EEST (+03:00)", "events": _calendar_today()}
    try:
        from skills.ceo._lib.memory import load_memory, extract_section
        mem = load_memory(["projects", "memory", "risks"])
        out["projects"] = (mem.get("projects", "") or "")[:4000]
        out["active_priorities"] = (
            extract_section(mem.get("memory", "") or "", "Active Priorities (this week)") or ""
        )[:2000]
        out["risks"] = (mem.get("risks", "") or "")[:2000]
    except Exception as exc:
        out["memory_error"] = str(exc)[:200]
    return out


def cmd_save(payload: dict) -> dict:
    meetings = payload.get("meetings") or []
    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        return {"saved": False, "reason": "no-sheet-configured", "count": 0}
    try:
        from skills.ceo._lib.sheets_meeting_sync import sync_meeting, GoogleApiGW, _now_iso
    except Exception as exc:
        return {"saved": False, "reason": f"import:{exc}", "count": 0}
    gw = GoogleApiGW()
    now = _now_iso()
    results = []
    for m in meetings:
        mid = (m.get("meeting_id")
               or f"{m.get('date', '')}/{m.get('time', '')}/{m.get('title', '')}").strip("/")
        try:
            res = sync_meeting(m, sheet_id, gw, now, meeting_id=mid)
            res["meeting_id"] = mid
            results.append(res)
        except Exception as exc:
            results.append({"meeting_written": False, "reason": str(exc)[:150], "meeting_id": mid})
    return {"saved": True,
            "count": sum(1 for r in results if r.get("meeting_written")),
            "results": results}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--gather", action="store_true")
    g.add_argument("--save", metavar="JSON", help="JSON {meetings:[...]} of agendas to upsert")
    args = ap.parse_args()

    if args.gather:
        result = cmd_gather()
    else:
        try:
            payload = json.loads(args.save)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --save expects JSON ({exc})", file=sys.stderr)
            return 2
        result = cmd_save(payload)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
