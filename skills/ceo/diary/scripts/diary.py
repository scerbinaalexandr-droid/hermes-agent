"""Daily diary + structured protocol helper for the /diary skill.

Two modes (mutually exclusive — never combined in one call):
  --gather              — emit JSON context (today's diary so far + recent days)
  --save '<JSON>'       — append a diary entry OR a meeting protocol to today's file

Storage layout under <logs>/diary/:
  YYYY-MM-DD.md         one append-only file per day (canonical artifact)

Each save appends a dated block to today's file. Two kinds of block:
  kind="entry"     → ### Diary (HH:MM) — free-form / structured daily entry
  kind="protocol"  → ### Protocol (HH:MM) — <topic>  (participants/decisions/actions)

Design notes
------------
- Writes ONLY to logs/diary/ (the diary's own space). It does NOT touch
  memory/*.md, so it stays decoupled and never trips the CEO-OS guard hook
  (scripts/hooks/guard.py). The spec asked for memory/diary/, but that path is
  blocked by the guard — Phase-1 boundary wins, so diary lives under logs/.
- Logs root resolved from HERMES_CEO_MEMORY_ROOT (exported by entrypoint as
  $HERMES_HOME/memory) → its parent /logs. On prod that is /opt/data/logs/diary
  (persists across deploys + included in the daily GitHub backup). Locally it
  falls back to <repo>/logs/diary. Mirrors coach_log.py's _logs_root().
- Privacy guard is the LLM's job in SKILL.md (Step 2). Helper trusts the JSON it
  receives (already shown to user for approval). Defence in depth: helper refuses
  obvious PII patterns (emails, card numbers, API keys, IBAN), mirroring notes.

Stdlib only — runs under cron python if ever needed.
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

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))
# Production fallback: _lib/ is baked into image at /opt/hermes, not synced via skill-sync.
if pathlib.Path("/opt/hermes/skills/ceo/_lib/memory.py").exists() and "/opt/hermes" not in sys.path:
    sys.path.insert(0, "/opt/hermes")

from skills.ceo._lib.memory import (  # noqa: E402
    last_entries,
    today_hhmm,
    today_iso,
)


# --- Defence-in-depth: refuse obvious sensitive patterns (mirror notes_log) --
_PII_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "email address"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "credit card number"),
    (re.compile(r"\b(?:sk|pk|api|token|secret)[-_][A-Za-z0-9]{20,}\b"), "API key / token"),
    (re.compile(r"\bIBAN[:\s]*[A-Z]{2}\d{2}[A-Z0-9]{4,}\b", re.IGNORECASE), "IBAN"),
]


def _scan_pii(text: str) -> list[str]:
    if not text:
        return []
    findings: list[str] = []
    for pattern, label in _PII_PATTERNS:
        if pattern.search(text):
            findings.append(label)
    return findings


def _logs_root() -> pathlib.Path:
    """Resolve the logs directory so diary artifacts persist + get backed up.

    Prod: HERMES_CEO_MEMORY_ROOT=/opt/data/memory → /opt/data/logs.
    Local/tests: $HERMES_HOME/logs, else <repo>/logs.
    """
    mem_root = os.environ.get("HERMES_CEO_MEMORY_ROOT")
    if mem_root:
        return pathlib.Path(mem_root).expanduser().resolve().parent / "logs"
    home = os.environ.get("HERMES_HOME")
    if home:
        return pathlib.Path(home).expanduser().resolve() / "logs"
    return _REPO / "logs"


def _diary_file(date: str) -> pathlib.Path:
    return _logs_root() / "diary" / f"{date}.md"


def _coerce_list(value) -> list[str]:
    """Accept list[str] or a single string; drop empties. Never fabricate."""
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value if str(v).strip()]


def _render_entry(payload: dict) -> str:
    """Render a free-form / structured daily diary entry block."""
    content = (payload.get("content") or "").strip()
    context = (payload.get("context") or "").strip()
    mood = (payload.get("mood") or "").strip()
    energy = (payload.get("energy") or "").strip()

    lines = [f"### Diary ({today_hhmm()})"]
    if context:
        lines.append(f"**Контекст:** {context}")
    if energy:
        lines.append(f"**Энергия:** {energy}")
    if mood:
        lines.append(f"**Настрой:** {mood}")
    lines.append("")
    lines.append(content)
    return "\n".join(lines)


def _render_protocol(payload: dict) -> str:
    """Render a structured meeting-protocol block."""
    topic = (payload.get("topic") or "Без темы").strip()
    participants = _coerce_list(payload.get("participants"))
    decisions = _coerce_list(payload.get("decisions"))
    actions = _coerce_list(payload.get("action_items"))
    summary = (payload.get("summary") or "").strip()
    raw = (payload.get("raw_text") or "").strip()

    lines = [f"### Protocol ({today_hhmm()}) — {topic}"]
    if participants:
        lines.append(f"**Участники:** {', '.join(participants)}")
    lines.append("")

    if decisions:
        lines.append("**Решения:**")
        lines.extend(f"- {d}" for d in decisions)
        lines.append("")

    if actions:
        lines.append("**Задачи:**")
        lines.extend(f"- [ ] {a}" for a in actions)
        lines.append("")

    if summary:
        lines.append("**Итог:**")
        lines.append(summary)
        lines.append("")

    if raw:
        lines.append("**Raw:**")
        lines.append("```")
        lines.append(raw)
        lines.append("```")

    return "\n".join(lines).rstrip()


def save(payload: dict) -> dict[str, object]:
    """Append a diary entry or protocol to today's diary file."""
    kind = (payload.get("kind") or "entry").strip().lower()
    if kind not in {"entry", "protocol"}:
        return {"error": f"unknown kind {kind!r}; expected 'entry' or 'protocol'"}

    # No-fake-data: refuse an empty payload rather than write a hollow block.
    if kind == "entry" and not (payload.get("content") or "").strip():
        return {"error": "entry requires non-empty 'content'"}
    if kind == "protocol" and not (payload.get("topic") or "").strip():
        return {"error": "protocol requires non-empty 'topic'"}

    # Defence-in-depth PII scan across the whole payload text.
    scan_text = " ".join(
        str(payload.get(f) or "")
        for f in ("content", "context", "topic", "summary", "raw_text")
    )
    scan_text += " " + " ".join(_coerce_list(payload.get("participants")))
    pii = _scan_pii(scan_text)
    if pii:
        return {
            "error": "refused: input contains sensitive data patterns",
            "patterns_found": pii,
            "guidance": (
                "redact the sensitive fields and retry. Helper hard-stops on "
                "emails, card numbers, API keys, IBAN."
            ),
        }

    date = (payload.get("date") or today_iso())[:10]
    try:
        _dt.date.fromisoformat(date)
    except ValueError:
        date = today_iso()

    block = _render_entry(payload) if kind == "entry" else _render_protocol(payload)

    path = _diary_file(date)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# Diary — {date}\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n\n{block}\n")

    return {
        "saved_path": str(path),
        "kind": kind,
        "date": date,
        "action_items_count": len(_coerce_list(payload.get("action_items"))),
        "sheet_sync": _sync_diary(payload, str(path)),
    }


def _sync_diary(payload: dict, saved_path: str) -> dict:
    """Best-effort mirror to Sheet: entry → Дневник, protocol → Протоколы. Never raises."""
    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        return {"synced": False, "reason": "no-sheet-configured"}
    script = os.environ.get("HERMES_SHEETS_SYNC",
                            "/opt/hermes/skills/ceo/_lib/sheets_meeting_sync.py")
    if not os.path.exists(script):
        script = str(pathlib.Path(__file__).resolve().parents[2] / "_lib" / "sheets_meeting_sync.py")
    kind = (payload.get("kind") or "entry").strip().lower()
    try:
        if kind == "protocol":
            cmd = [sys.executable, script, "--save", json.dumps(payload, ensure_ascii=False),
                   "--note-id", saved_path]
            area = payload.get("area")
            if area:
                cmd += ["--area", str(area)]
        else:
            cmd = [sys.executable, script, "--diary",
                   "--save", json.dumps(payload, ensure_ascii=False)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if r.returncode == 0:
            try:
                return {"synced": True, **json.loads((r.stdout or "").strip() or "{}")}
            except Exception:
                return {"synced": True, "raw": (r.stdout or "").strip()[:200]}
        return {"synced": False, "reason": ((r.stdout or "") + (r.stderr or "")).strip()[:200]}
    except Exception as exc:
        return {"synced": False, "reason": str(exc)[:200]}


def gather() -> dict[str, object]:
    """Context for the diary: today's file so far + recent daily_log days.

    Read-only. Lets the LLM append rather than duplicate within the same day,
    and gives light awareness of recent activity (no fabrication).
    """
    date = today_iso()
    weekday = _dt.date.today().strftime("%A")

    today_file = _diary_file(date)
    today_diary = today_file.read_text(encoding="utf-8") if today_file.exists() else ""

    # Count existing blocks today (### Diary / ### Protocol headers).
    today_blocks = len(re.findall(r"^###\s+(Diary|Protocol)\b", today_diary, flags=re.MULTILINE))

    # Light recent-activity context from the canonical daily_log (read-only).
    try:
        recent_days = last_entries("daily_log", limit=3)
    except Exception:
        recent_days = []

    return {
        "date": date,
        "weekday": weekday,
        "diary_file": str(today_file),
        "today_blocks": today_blocks,
        "today_diary": today_diary,
        "recent_daily_log": recent_days,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CEO diary + protocol helper.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--gather", action="store_true", help="Emit context JSON (read-only).")
    group.add_argument("--save", metavar="JSON", help="Append a diary entry or protocol (JSON payload).")
    args = parser.parse_args()

    if args.gather:
        json.dump(gather(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    try:
        payload = json.loads(args.save)
    except json.JSONDecodeError as e:
        print(f"ERROR: --save expects a JSON object: {e}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("ERROR: --save JSON must be an object/dict.", file=sys.stderr)
        return 2

    result = save(payload)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
