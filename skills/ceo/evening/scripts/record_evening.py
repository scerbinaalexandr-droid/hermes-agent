"""Evening review helper for /evening skill.

Two modes:
  --gather                — emit JSON context the agent uses to phrase the question
  --save '<JSON-fields>'  — persist a parsed evening review to logs + memory
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import re
import sys

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

from skills.ceo._lib.memory import (  # noqa: E402
    _resolve,
    append_entry,
    assert_memory_present,
    last_entries,
    load_memory,
    projects_by_priority,
    risks_by_severity,
    today_hhmm,
    today_iso,
)


FIELD_ORDER = [
    "completed",
    "not_completed",
    "why",
    "carry_over",
    "main_bottleneck",
    "energy_level",
    "stress_level",
    "health_status",
    "family_status",
    "lesson_learned",
    "tomorrow_focus",
]

FIELD_LABEL = {
    "completed": "Completed",
    "not_completed": "Not Completed",
    "why": "Why",
    "carry_over": "Carry Over",
    "main_bottleneck": "Main Bottleneck",
    "energy_level": "Energy Level",
    "stress_level": "Stress Level",
    "health_status": "Health Status",
    "family_status": "Family Status",
    "lesson_learned": "Lesson Learned",
    "tomorrow_focus": "Tomorrow Focus",
}


def gather() -> dict[str, object]:
    """Context for the agent to compose the evening prompt."""
    assert_memory_present(["soul", "daily_log", "projects", "risks"])
    date = today_iso()
    weekday = _dt.date.today().strftime("%A")

    # Today's daily_log entries: pull the last block if it matches today.
    log_blocks = last_entries("daily_log", limit=5)
    today_log_entries = [b for b in log_blocks if b.startswith(date)]

    # Per-day log file content (logs/daily/YYYY-MM-DD.md)
    per_day = _REPO / "logs" / "daily" / f"{date}.md"
    today_per_day = per_day.read_text(encoding="utf-8") if per_day.exists() else ""

    return {
        "date": date,
        "weekday": weekday,
        "today_log_entries": today_log_entries,
        "today_per_day_log": today_per_day,
        "high_priority_projects": projects_by_priority("high"),
        "top_risks": risks_by_severity("medium")[:3],
    }


def _format_review_block(fields: dict[str, str]) -> str:
    """Render the structured review for logs/daily/YYYY-MM-DD.md."""
    lines = []
    for key in FIELD_ORDER:
        label = FIELD_LABEL[key]
        val = (fields.get(key) or "").strip() or "(not provided)"
        lines.append(f"**{label}:** {val}")
    return "\n\n".join(lines)


def _short_summary(fields: dict[str, str]) -> str:
    """Two-three line summary for memory/daily_log.md accumulator."""
    energy = fields.get("energy_level", "—")
    stress = fields.get("stress_level", "—")
    focus = (fields.get("tomorrow_focus") or "(not provided)").splitlines()[0][:120]
    bottleneck = (fields.get("main_bottleneck") or "(not provided)").splitlines()[0][:120]
    return (
        f"### Evening ({today_hhmm()})\n"
        f"Energy {energy}/10 · Stress {stress}/10 · Bottleneck: {bottleneck}\n"
        f"Tomorrow focus: {focus}"
    )


def _update_tomorrow_priorities(tomorrow_focus: str, carry_over: str) -> None:
    """Refresh memory/memory.md::Active Priorities (this week) with tomorrow_focus + carry-over.

    Safe-edit: only replaces the body of that exact section. Other sections
    untouched.
    """
    path = _resolve("memory")
    text = path.read_text(encoding="utf-8")
    header = "Active Priorities (this week)"
    pattern = re.compile(
        rf"(^##\s+{re.escape(header)}\s*\n)(.*?)(?=^##\s|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    new_block_lines: list[str] = []
    if tomorrow_focus.strip():
        for line in tomorrow_focus.splitlines():
            stripped = line.strip(" -*•").strip()
            if not stripped:
                continue
            new_block_lines.append(f"- [ ] {stripped}")
    if carry_over.strip() and "(not provided)" not in carry_over.lower():
        for line in carry_over.splitlines():
            stripped = line.strip(" -*•").strip()
            if not stripped:
                continue
            new_block_lines.append(f"- [ ] (carry-over) {stripped}")
    if not new_block_lines:
        new_block_lines.append("- [ ] (no focus captured at evening review)")
    new_body = (
        "\n".join(new_block_lines)
        + f"\n\n_Last refreshed by /evening at {today_iso()} {today_hhmm()}_\n\n"
    )
    if not m:
        text = text.rstrip() + f"\n\n## {header}\n\n{new_body}"
    else:
        text = text[: m.start(2)] + new_body + text[m.end(2) :]
    path.write_text(text, encoding="utf-8")


def save(fields: dict[str, str]) -> dict[str, str]:
    """Persist evening review. Returns paths touched."""
    assert_memory_present(["daily_log", "memory"])
    date = today_iso()

    # Per-day full log
    per_day = _REPO / "logs" / "daily" / f"{date}.md"
    per_day.parent.mkdir(parents=True, exist_ok=True)
    if not per_day.exists():
        per_day.write_text(f"# Daily Log — {date}\n", encoding="utf-8")
    block = _format_review_block(fields)
    with per_day.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## Evening ({today_hhmm()})\n\n{block}\n")

    # Short accumulated entry
    append_entry("daily_log", date, _short_summary(fields))

    # Update tomorrow's priorities in memory.md
    _update_tomorrow_priorities(
        fields.get("tomorrow_focus", "") or "",
        fields.get("carry_over", "") or "",
    )

    return {
        "per_day_log": str(per_day),
        "daily_log": "memory/daily_log.md",
        "memory_priorities_updated": "memory/memory.md::Active Priorities (this week)",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--gather", action="store_true", help="Emit context JSON for the prompt.")
    group.add_argument("--save", metavar="JSON", help="Persist a parsed evening review.")
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
