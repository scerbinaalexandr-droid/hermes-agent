"""Deterministic skeleton renderer for daily executive briefing.

LLM-side (the agent running the daily_briefing skill) handles narrative
generation (Main Focus phrasing, One Important Question). This script handles
the deterministic parts — section gathering, project filtering, log append.

Usage from the skill execute step:

    python skills/ceo/daily_briefing/scripts/render_briefing.py --collect
        # Prints a JSON blob with all loaded sections for LLM consumption.

    python skills/ceo/daily_briefing/scripts/render_briefing.py --log "<final text>"
        # Appends provided final briefing to logs/daily/YYYY-MM-DD.md and
        # memory/daily_log.md.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

# Make project root importable so we can use the shared CEO memory helper.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT))
# Production fallback: skills/ceo/_lib/ lives only in /opt/hermes (built
# into image). Hermes skill-sync to /opt/data copies only skill dirs with
# SKILL.md; _lib/ has no SKILL.md so it stays in image path only.
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

from skills.ceo._lib.memory import (  # noqa: E402
    append_entry,
    assert_memory_present,
    last_entries,
    load_memory,
    projects_by_priority,
    today_iso,
)


def collect() -> dict[str, object]:
    """Gather everything LLM needs to compose the briefing."""
    assert_memory_present(
        required=["soul", "user", "memory", "areas", "projects", "risks", "daily_log"]
    )
    files = load_memory(["soul", "user", "memory", "areas", "projects", "risks"])
    return {
        "date": today_iso(),
        "weekday": _dt.date.today().strftime("%A"),
        "soul": files["soul"],
        "user": files["user"],
        "memory": files["memory"],
        "areas": files["areas"],
        "projects_full": files["projects"],
        "risks": files["risks"],
        "high_priority_projects": projects_by_priority("high"),
        "medium_priority_projects": projects_by_priority("medium"),
        "recent_daily_log": last_entries("daily_log", limit=3),
    }


def write_logs(final_text: str) -> dict[str, str]:
    """Append final briefing to per-day log + accumulator log."""
    date = today_iso()
    now_hhmm = _dt.datetime.now().strftime("%H:%M")

    # Per-day full log: logs/daily/YYYY-MM-DD.md
    per_day = _REPO_ROOT / "logs" / "daily" / f"{date}.md"
    per_day.parent.mkdir(parents=True, exist_ok=True)
    if not per_day.exists():
        per_day.write_text(f"# Daily Log — {date}\n", encoding="utf-8")
    with per_day.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## Brief ({now_hhmm})\n\n{final_text.rstrip()}\n")

    # Short summary into memory/daily_log.md
    short = final_text.splitlines()
    main_focus_line = next(
        (l for l in short if l.lower().startswith("main focus") or l.startswith("Main Focus")),
        "",
    ).strip()
    summary = f"### Brief ({now_hhmm})\n{main_focus_line or '(see logs/daily for full text)'}"
    append_entry("daily_log", date, summary)

    return {"per_day_log": str(per_day), "accumulated_log": "memory/daily_log.md"}


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--collect", action="store_true", help="Print collected sections as JSON.")
    group.add_argument("--log", metavar="TEXT", help="Append final briefing TEXT to logs.")
    args = parser.parse_args()

    if args.collect:
        json.dump(collect(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.log:
        result = write_logs(args.log)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
