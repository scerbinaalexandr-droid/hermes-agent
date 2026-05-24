"""Coaching session helper for the /coach skill.

Two modes:
  --gather                — emit JSON context the coach uses to personalize the session
  --save '<JSON-fields>'  — persist a coaching-session artifact to logs/coaching/

Design notes
------------
- v1 writes ONLY to logs/coaching/YYYY-MM-DD.md (the coach's own space). It does
  NOT touch memory/*.md, so it stays fully decoupled from the rest of CEO OS and
  never trips the CEO-OS guard hook (scripts/hooks/guard.py).
- Logs root is resolved from HERMES_CEO_MEMORY_ROOT (exported by the entrypoint as
  $HERMES_HOME/memory) → its parent /logs. On prod that is /opt/data/logs/coaching
  (persists across deploys + included in the daily GitHub backup). Locally it falls
  back to <repo>/logs/coaching. This deliberately avoids the `_REPO/logs` path used
  by record_evening.py, which lands in the ephemeral in-image dir after symlink
  resolution and is not backed up.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

from skills.ceo._lib.memory import (  # noqa: E402
    last_entries,
    load_memory,
    projects_by_priority,
    today_hhmm,
    today_iso,
)

# Memory files that serve as the coach's "context about me" (no duplicate file).
_CONTEXT_FILES = ["user", "goals", "areas", "memory"]


def _logs_root() -> pathlib.Path:
    """Resolve the logs directory so coaching artifacts persist + get backed up.

    Prod: HERMES_CEO_MEMORY_ROOT=/opt/data/memory → /opt/data/logs.
    Local/tests: <repo>/logs.
    """
    mem_root = os.environ.get("HERMES_CEO_MEMORY_ROOT")
    if mem_root:
        return pathlib.Path(mem_root).expanduser().resolve().parent / "logs"
    home = os.environ.get("HERMES_HOME")
    if home:
        return pathlib.Path(home).expanduser().resolve() / "logs"
    return _REPO / "logs"


def _coaching_file(date: str) -> pathlib.Path:
    return _logs_root() / "coaching" / f"{date}.md"


def gather() -> dict[str, object]:
    """Context for the coach to personalize the session.

    Soft-loads memory: missing files come back with a marker, never raises — a
    coaching session is useful even with sparse context.
    """
    date = today_iso()
    weekday = _dt.date.today().strftime("%A")

    ctx = load_memory(_CONTEXT_FILES)
    context = {name: ctx.get(name, "") for name in _CONTEXT_FILES}

    # Today's coaching log so a second session today appends rather than duplicates.
    today_file = _coaching_file(date)
    today_coaching = today_file.read_text(encoding="utf-8") if today_file.exists() else ""

    return {
        "date": date,
        "weekday": weekday,
        "context": context,  # user / goals / areas / memory markdown (the "about me")
        "high_priority_projects": projects_by_priority("high"),
        "recent_days": last_entries("daily_log", limit=5),
        "today_coaching": today_coaching,
    }


def save(fields: dict[str, str]) -> dict[str, str]:
    """Append a coaching-session artifact to logs/coaching/YYYY-MM-DD.md."""
    date = today_iso()
    session_type = (fields.get("session_type") or "Свободная").strip()
    artifact = (fields.get("artifact") or "").strip()
    if not artifact:
        artifact = "(сессия без зафиксированного артефакта)"

    path = _coaching_file(date)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# Coaching Log — {date}\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## Coach — {session_type} ({today_hhmm()})\n\n{artifact}\n")

    return {"coaching_log": str(path), "session_type": session_type}


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--gather", action="store_true", help="Emit context JSON for the session.")
    group.add_argument("--save", metavar="JSON", help="Persist a coaching-session artifact.")
    args = parser.parse_args()

    if args.gather:
        json.dump(gather(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.save:
        try:
            fields = json.loads(args.save)
        except json.JSONDecodeError as e:
            print(f"ERROR: --save expects JSON object: {e}", file=sys.stderr)
            return 2
        if not isinstance(fields, dict):
            print("ERROR: --save JSON must be an object/dict.", file=sys.stderr)
            return 2
        result = save(fields)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
