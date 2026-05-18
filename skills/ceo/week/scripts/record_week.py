"""Weekly CEO review helper for /week skill.

Modes:
  --gather                — emit JSON context for the prompt
  --save '<JSON-fields>'  — persist a parsed weekly review
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

from skills.ceo._lib.memory import (  # noqa: E402
    all_projects,
    append_entry,
    assert_memory_present,
    iso_week,
    last_entries,
    risks_by_severity,
    today_hhmm,
    today_iso,
    update_project_field,
)


FIELD_ORDER = [
    "business",
    "cashflow",
    "sales",
    "production",
    "marketing",
    "team",
    "projects",  # rendered separately — list of dicts
    "health",
    "family",
    "recovery",
    "learning",
    "key_risks_changed",
    "key_decisions",
    "next_week_focus",
]

FIELD_LABEL = {
    "business": "Business",
    "cashflow": "Cashflow",
    "sales": "Sales",
    "production": "Production",
    "marketing": "Marketing",
    "team": "Team",
    "projects": "Projects",
    "health": "Health",
    "family": "Family",
    "recovery": "Recovery",
    "learning": "Learning",
    "key_risks_changed": "Key Risks Changed",
    "key_decisions": "Key Decisions",
    "next_week_focus": "Next Week Focus",
}


def _week_bounds() -> tuple[_dt.date, _dt.date]:
    today = _dt.date.today()
    year, week, weekday = today.isocalendar()  # weekday: Mon=1 .. Sun=7
    monday = today - _dt.timedelta(days=weekday - 1)
    sunday = monday + _dt.timedelta(days=6)
    return monday, sunday


def gather() -> dict[str, object]:
    assert_memory_present(["soul", "projects", "risks", "daily_log", "weekly_review"])
    monday, sunday = _week_bounds()

    # Pull daily_log entries falling within the week (header == YYYY-MM-DD).
    week_set = {
        (monday + _dt.timedelta(days=i)).isoformat() for i in range(7)
    }
    candidate_entries = last_entries("daily_log", limit=20)
    in_week = [e for e in candidate_entries if e.split("\n", 1)[0].strip() in week_set]

    last_weekly = last_entries("weekly_review", limit=1)

    return {
        "iso_week": iso_week(),
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "today_is_sunday": _dt.date.today().weekday() == 6,
        "daily_log_entries_this_week": in_week,
        "all_projects": all_projects(),
        "top_risks": risks_by_severity("medium")[:3],
        "last_weekly_review": last_weekly[0] if last_weekly else "",
    }


def _format_projects_block(projects: list[dict[str, str]]) -> tuple[str, list[str], list[str]]:
    """Render projects section + return (rendered, matched_names, unmatched_names)."""
    if not projects:
        return "_(no project status updates this week)_", [], []
    rendered: list[str] = []
    matched: list[str] = []
    unmatched: list[str] = []
    known = {p["name"]: p for p in all_projects()}
    for entry in projects:
        name = (entry.get("name") or "").strip()
        status = (entry.get("status") or "").strip()
        note = (entry.get("note") or "").strip()
        line = f"- **{name}**"
        if status:
            line += f" — status: `{status}`"
        if note:
            line += f" — {note}"
        rendered.append(line)
        if name in known:
            matched.append(name)
        else:
            unmatched.append(name)
    return "\n".join(rendered), matched, unmatched


def _format_review_block(fields: dict[str, object]) -> tuple[str, list[str], list[str]]:
    parts: list[str] = []
    matched: list[str] = []
    unmatched: list[str] = []
    for key in FIELD_ORDER:
        label = FIELD_LABEL[key]
        if key == "projects":
            projects = fields.get("projects") or []
            rendered, matched, unmatched = _format_projects_block(projects)
            parts.append(f"**{label}:**\n{rendered}")
            continue
        val = fields.get(key)
        val_str = (val or "").strip() if isinstance(val, str) else "(not provided)"
        if not val_str:
            val_str = "(not provided)"
        parts.append(f"**{label}:** {val_str}")
    return "\n\n".join(parts), matched, unmatched


def _short_summary(fields: dict[str, object]) -> str:
    next_focus = fields.get("next_week_focus") or "(not provided)"
    if isinstance(next_focus, str):
        next_focus = next_focus.splitlines()[0][:120]
    risks_changed = fields.get("key_risks_changed") or "(none)"
    if isinstance(risks_changed, str):
        risks_changed = risks_changed.splitlines()[0][:120]
    return (
        f"Next week focus: {next_focus}\n"
        f"Risks changed: {risks_changed}"
    )


def save(fields: dict[str, object]) -> dict[str, object]:
    assert_memory_present(["weekly_review", "projects"])
    week = iso_week()
    block, matched, unmatched = _format_review_block(fields)

    # Per-week log
    per_week = _REPO / "logs" / "weekly" / f"{week}.md"
    per_week.parent.mkdir(parents=True, exist_ok=True)
    if not per_week.exists():
        per_week.write_text(f"# Weekly Log — {week}\n", encoding="utf-8")
    with per_week.open("a", encoding="utf-8") as f:
        f.write(f"\n\n## Review ({today_iso()} {today_hhmm()})\n\n{block}\n")

    # Append-only accumulated entry
    append_entry("weekly_review", week, _short_summary(fields))

    # Update each matched project's Status + Last Update in projects.md
    updated_projects: list[str] = []
    project_updates = fields.get("projects") or []
    for entry in project_updates:
        name = (entry.get("name") or "").strip()
        status = (entry.get("status") or "").strip()
        if not name or name not in matched:
            continue
        if status and update_project_field(name, "Status", status):
            updated_projects.append(name)
        update_project_field(name, "Last Update", today_iso())

    return {
        "per_week_log": str(per_week),
        "weekly_review": "memory/weekly_review.md",
        "projects_updated": updated_projects,
        "projects_unmatched": unmatched,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--gather", action="store_true")
    group.add_argument("--save", metavar="JSON")
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
