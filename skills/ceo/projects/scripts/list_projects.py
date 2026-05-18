"""Projects listing helper for /projects skill.

Returns JSON with active projects (skipping Archived section), optionally
filtered by priority. Caller (agent) formats for Telegram per SKILL.md.
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

from skills.ceo._lib.memory import all_projects, _normalize_rank_token  # noqa: E402


_PRIORITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "": 0}


def _parse_deadline(raw: str) -> tuple[int, str]:
    """Return (sort_key, display). Non-date deadlines sort to the end."""
    raw = (raw or "").strip()
    if not raw:
        return (10**9, "—")
    # Try to extract leading YYYY-MM-DD (the rest may be a parenthetical note).
    try:
        # Strip parens/notes
        head = raw.split("(", 1)[0].strip()
        d = _dt.date.fromisoformat(head)
        return (d.toordinal(), raw)
    except Exception:
        # rolling / continuous / none / ad-hoc — push to end
        return (10**9, raw)


def _first_next_action(proj: dict[str, str]) -> str:
    raw = (proj.get("next_actions_list") or "").strip()
    if not raw:
        return ""
    return raw.splitlines()[0].strip()


def gather(priority_filter: str | None = None) -> dict[str, object]:
    projects = all_projects()
    enriched: list[dict[str, object]] = []
    for p in projects:
        status_raw = (p.get("status") or "").strip()
        status_norm = _normalize_rank_token(status_raw)
        # Skip done projects (Archived section already excluded by parser).
        if status_norm == "done":
            continue
        priority = _normalize_rank_token(p.get("priority", ""))
        if priority_filter and priority != priority_filter.lower():
            continue
        deadline_raw = p.get("deadline") or ""
        sort_key, display = _parse_deadline(deadline_raw)
        enriched.append({
            "name": p["name"],
            "status": status_norm or "(unset)",
            "status_raw": status_raw,
            "priority": priority or "(unset)",
            "deadline": display,
            "deadline_sort_key": sort_key,
            "priority_rank": _PRIORITY_RANK.get(priority, 0),
            "last_update": p.get("last_update", ""),
            "next_action_first": _first_next_action(p),
        })
    enriched.sort(
        key=lambda r: (-r["priority_rank"], r["deadline_sort_key"], r["name"]),
    )
    return {
        "filter": priority_filter or None,
        "total": len(enriched),
        "projects": enriched,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--priority",
        choices=["critical", "high", "medium", "low"],
        help="Filter projects to a single priority level.",
    )
    args = parser.parse_args()
    json.dump(gather(args.priority), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
