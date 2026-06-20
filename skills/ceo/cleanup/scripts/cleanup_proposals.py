"""Memory-hygiene PROPOSAL helper for the /cleanup skill (Stage 5c).

READ-ONLY by design. Scans memory/*.md (areas, goals, projects, risks, memory,
daily_log, decisions) and emits a deterministic JSON list of hygiene proposals
for the CEO to apply manually or approve. It NEVER writes to memory/* —
scripts/hooks/guard.py blocks memory writes, and this script has no write path
at all (no --save). The only mode is --gather.

What it proposes (each with a real, cited source field/date — NO fabrication):
  - stale projects/risks   — Last Update / Last Reviewed older than --stale-days
  - overdue project review — Next Review date in the past
  - done-but-listed        — project Status=done still in Active list
  - closed-but-listed risk — risk Status=closed|mitigated still in active section
  - overdue decision       — decision Review Date passed, Status still pending
  - placeholder leftovers  — template '<...>' values never filled in
  - overgrown priorities   — memory.md Active Priorities exceeds --max-priorities
  - duplicate priorities    — exact-duplicate bullets in Active Priorities
  - daily_log archive       — '## YYYY-MM-DD' entries older than --archive-days

Each proposal is a suggestion only. The script proposes; the user disposes.
Stdlib only. sys.path fallback to /opt/hermes for prod. No LLM, no network.
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
# Production fallback: _lib/ is baked into image at /opt/hermes, not synced via skill-sync.
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

from skills.ceo._lib.memory import (  # noqa: E402
    all_projects,
    all_risks,
    extract_section,
    load_memory,
    memory_root,
    today_iso,
)

# Defaults tuned to blueprint cadence (weekly review = 7d, memory window = 2-4 weeks).
DEFAULT_STALE_DAYS = 30
DEFAULT_ARCHIVE_DAYS = 30
DEFAULT_MAX_PRIORITIES = 7

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_DAILY_HEADER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
# A leftover template placeholder like '<Specific cashflow risk>' or '<action>'.
_PLACEHOLDER_RE = re.compile(r"<[^<>\n]{2,60}>")
# Strip fenced ```...``` blocks (format templates/examples) so a template line is
# never parsed as real data — guards against NO-FAKE-IDENTIFIERS violations.
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

# Risk statuses that mean "no longer an active threat" → should not sit in the
# active risk list.
_RISK_CLOSED = {"closed", "mitigated", "resolved"}


def _today() -> _dt.date:
    return _dt.date.fromisoformat(today_iso())


def _parse_date(raw: str) -> _dt.date | None:
    """Extract the first YYYY-MM-DD from a field; None if absent/placeholder."""
    if not raw:
        return None
    m = _DATE_RE.search(raw)
    if not m:
        return None
    try:
        return _dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _age_days(d: _dt.date, today: _dt.date) -> int:
    return (today - d).days


def _proposal(kind: str, target: str, detail: str, source: str, action: str) -> dict[str, str]:
    """One proposal. `source` cites the real field/date the signal came from.

    `action` = the suggested manual edit (the user applies it; the skill never does).
    """
    return {
        "kind": kind,
        "target": target,
        "detail": detail,
        "source": source,
        "suggested_action": action,
    }


def _scan_projects(today: _dt.date, stale_days: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for p in all_projects():
        name = p.get("name", "(unnamed)")
        status = (p.get("status") or "").strip().lower()

        # done-but-listed: a finished project still in the active file.
        if status.startswith("done") or status.startswith("complete"):
            out.append(_proposal(
                "done_but_listed",
                f"project «{name}»",
                f"Статус «{status}», но проект всё ещё в active-списке.",
                f"projects.md → «{name}» → Status: {p.get('status', '')}",
                "Перенести блок в раздел «Archived» в memory/projects.md.",
            ))

        # stale: Last Update older than threshold.
        lu = _parse_date(p.get("last_update", ""))
        if lu is not None:
            age = _age_days(lu, today)
            if age > stale_days and not status.startswith("done"):
                out.append(_proposal(
                    "stale_project",
                    f"project «{name}»",
                    f"Last Update {lu.isoformat()} — {age} дн. без обновления (порог {stale_days}).",
                    f"projects.md → «{name}» → Last Update: {lu.isoformat()}",
                    "Обновить через /capture или /week, либо закрыть проект.",
                ))

        # overdue review.
        nr = _parse_date(p.get("next_review", ""))
        if nr is not None and nr < today:
            out.append(_proposal(
                "overdue_review",
                f"project «{name}»",
                f"Next Review {nr.isoformat()} прошёл ({_age_days(nr, today)} дн. назад).",
                f"projects.md → «{name}» → Next Review: {nr.isoformat()}",
                "Провести ревью и выставить новую дату Next Review.",
            ))

        # placeholder leftovers in key fields.
        for field in ("goal", "deadline", "next_review"):
            val = p.get(field, "")
            if _PLACEHOLDER_RE.search(val):
                out.append(_proposal(
                    "placeholder",
                    f"project «{name}»",
                    f"Поле {field} осталось шаблонным: {val.strip()}",
                    f"projects.md → «{name}» → {field}: {val.strip()}",
                    f"Заполнить реальное значение поля {field}.",
                ))
    return out


def _scan_risks(today: _dt.date, stale_days: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for r in all_risks():
        title = r.get("title", "(untitled)")
        status = (r.get("status") or "").strip().lower()

        if status in _RISK_CLOSED:
            out.append(_proposal(
                "closed_but_listed",
                f"risk «{title}»",
                f"Статус «{status}», но риск всё ещё в активном разделе risks.md.",
                f"risks.md → «{title}» → Status: {r.get('status', '')}",
                "Удалить блок или перенести в архив рисков.",
            ))

        lr = _parse_date(r.get("last_reviewed", ""))
        if lr is not None and status not in _RISK_CLOSED:
            age = _age_days(lr, today)
            if age > stale_days:
                out.append(_proposal(
                    "stale_risk",
                    f"risk «{title}»",
                    f"Last Reviewed {lr.isoformat()} — {age} дн. без ревью (порог {stale_days}).",
                    f"risks.md → «{title}» → Last Reviewed: {lr.isoformat()}",
                    "Пересмотреть риск и обновить Last Reviewed.",
                ))
    return out


def _scan_decisions(today: _dt.date, raw_text: str) -> list[dict[str, str]]:
    """Overdue decisions: Review Date passed and Status still pending.

    Real decisions in memory/decisions.md use level-2 headers
    ('## YYYY-MM-DD — slug'); the file's `## Format` block carries a '###'
    template inside a ```markdown fence. We strip fenced blocks FIRST so the
    placeholder template can never be misread as a real decision (NO FAKE
    IDENTIFIERS), then split on level-2 headers to match real decisions, and
    skip any header still holding a 'YYYY' / '<...>' placeholder token.
    """
    out: list[dict[str, str]] = []
    cleaned = _FENCE_RE.sub("", raw_text)
    blocks = re.split(r"^##\s+", cleaned, flags=re.MULTILINE)
    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        header = lines[0].strip()
        if "YYYY" in header or _PLACEHOLDER_RE.search(header):
            continue
        fields: dict[str, str] = {}
        for line in lines[1:]:
            s = line.strip()
            if ":" in s and not s.startswith("-"):
                key, _, val = s.partition(":")
                fields[key.strip().lower().replace(" ", "_")] = val.strip()
        status = (fields.get("status") or "").strip().lower()
        rd = _parse_date(fields.get("review_date", ""))
        if rd is not None and rd < today and status in {"", "pending"}:
            out.append(_proposal(
                "overdue_decision",
                f"decision «{header}»",
                f"Review Date {rd.isoformat()} прошёл, статус всё ещё «{status or 'pending'}».",
                f"decisions.md → «{header}» → Review Date: {rd.isoformat()}",
                "Провести ревью решения и обновить Status (applied/reviewed/reversed).",
            ))
    return out


def _scan_memory_priorities(
    mem_text: str, max_priorities: int
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    section = extract_section(mem_text, "Active Priorities (this week)")
    if section is None:
        return out
    bullets = [
        ln.strip()
        for ln in section.splitlines()
        if ln.strip().startswith("-") and not _PLACEHOLDER_RE.search(ln)
    ]
    # overgrown
    if len(bullets) > max_priorities:
        out.append(_proposal(
            "overgrown_priorities",
            "memory.md → Active Priorities",
            f"{len(bullets)} приоритетов (порог {max_priorities}) — список разросся.",
            "memory.md → ## Active Priorities (this week)",
            f"Оставить топ-{max_priorities}, выполненные перенести в daily_log, "
            "остальные — в проекты.",
        ))
    # exact-duplicate bullets
    seen: dict[str, int] = {}
    for b in bullets:
        norm = re.sub(r"\s+", " ", b.lower()).strip()
        seen[norm] = seen.get(norm, 0) + 1
    for norm, count in seen.items():
        if count > 1:
            out.append(_proposal(
                "duplicate_priority",
                "memory.md → Active Priorities",
                f"Дубль приоритета ×{count}: {norm[:80]}",
                "memory.md → ## Active Priorities (this week)",
                "Удалить дублирующиеся строки, оставить одну.",
            ))
    return out


def _scan_daily_log(today: _dt.date, raw_text: str, archive_days: int) -> list[dict[str, str]]:
    """Propose archiving daily_log entries whose date is older than the window."""
    dates: list[_dt.date] = []
    for m in _DAILY_HEADER_RE.finditer(raw_text):
        d = _parse_date(m.group(1))
        if d is not None:
            dates.append(d)
    old = sorted(d for d in dates if _age_days(d, today) > archive_days)
    if not old:
        return []
    span = f"{old[0].isoformat()} … {old[-1].isoformat()}"
    return [_proposal(
        "daily_log_archive",
        "memory.md/daily_log",
        f"{len(old)} записей старше {archive_days} дн. ({span}).",
        f"daily_log.md → {len(old)} entries dated {span}",
        f"Перенести записи старше {archive_days} дн. в logs/daily/ "
        "(append-only лог не редактируем вручную — архивируем срезом).",
    )]


def gather(
    stale_days: int,
    archive_days: int,
    max_priorities: int,
) -> dict[str, object]:
    today = _today()
    raw = load_memory(["projects", "risks", "decisions", "memory", "daily_log"])

    proposals: list[dict[str, str]] = []
    proposals += _scan_projects(today, stale_days)
    proposals += _scan_risks(today, stale_days)
    proposals += _scan_decisions(today, raw.get("decisions", ""))
    proposals += _scan_memory_priorities(raw.get("memory", ""), max_priorities)
    proposals += _scan_daily_log(today, raw.get("daily_log", ""), archive_days)

    by_kind: dict[str, int] = {}
    for p in proposals:
        by_kind[p["kind"]] = by_kind.get(p["kind"], 0) + 1

    return {
        "generated": today.isoformat(),
        "memory_root": str(memory_root()),
        "thresholds": {
            "stale_days": stale_days,
            "archive_days": archive_days,
            "max_priorities": max_priorities,
        },
        "total": len(proposals),
        "by_kind": by_kind,
        "proposals": proposals,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit memory-hygiene proposals as JSON (read-only, never writes memory)."
    )
    # Single read-only mode. No --save: this skill proposes, the user disposes.
    parser.add_argument(
        "--gather",
        action="store_true",
        required=True,
        help="Emit proposals JSON to stdout (read-only).",
    )
    parser.add_argument(
        "--stale-days", type=int, default=DEFAULT_STALE_DAYS,
        help=f"Days without update before project/risk is flagged stale (default {DEFAULT_STALE_DAYS}).",
    )
    parser.add_argument(
        "--archive-days", type=int, default=DEFAULT_ARCHIVE_DAYS,
        help=f"Days before daily_log entries are proposed for archive (default {DEFAULT_ARCHIVE_DAYS}).",
    )
    parser.add_argument(
        "--max-priorities", type=int, default=DEFAULT_MAX_PRIORITIES,
        help=f"Active Priorities count above which the list is flagged overgrown (default {DEFAULT_MAX_PRIORITIES}).",
    )
    args = parser.parse_args()

    result = gather(args.stale_days, args.archive_days, args.max_priorities)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
