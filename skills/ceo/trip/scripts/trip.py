"""Trip / business-travel planner for the /trip skill (CEO OS).

Two modes (mutually exclusive — never combined in one call):
  --gather              — emit JSON context (recent trips, for dedup awareness)
  --save '<JSON>'       — persist a trip plan as a per-trip markdown file

Storage layout under <logs>/trips/:
  YYYY-MM-DD-<destination-slug>.md     one file per trip plan (canonical artifact)

Each save also best-effort mirrors the trip into the master Google Sheet
(Поездки tab via _lib/sheets_meeting_sync.py) so trips accumulate as structured
rows for later analytics. The markdown lives under logs/ (persists across
deploys on prod + included in the daily GitHub backup); the Sheet is the
analytical archive in Hermes's Google Drive.

Design mirrors diary.py / notes_log.py:
- Writes ONLY to logs/trips/ — never memory/*.md, so it never trips the CEO-OS
  guard hook (scripts/hooks/guard.py). Phase-1 boundary wins.
- Logs root resolved from HERMES_CEO_MEMORY_ROOT (exported by entrypoint as
  $HERMES_HOME/memory) → its parent /logs. On prod: /opt/data/logs/trips.
- Privacy guard is the LLM's job in SKILL.md. Defence in depth: helper refuses
  obvious PII patterns (emails, card numbers, API keys, IBAN).

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

from skills.ceo._lib.memory import today_iso  # noqa: E402


# --- Defence-in-depth: refuse obvious sensitive patterns (mirror diary) ------
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
    """Resolve the logs directory so trip artifacts persist + get backed up.

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


def _trips_dir() -> pathlib.Path:
    return _logs_root() / "trips"


def _slugify(text: str, max_len: int = 40) -> str:
    """Filesystem-safe slug. Transliterates basic Cyrillic, drops the rest."""
    cyrillic_map = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    out = []
    for ch in text.lower():
        if ch in cyrillic_map:
            out.append(cyrillic_map[ch])
        elif ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    slug = re.sub(r"-+", "-", "".join(out)).strip("-")
    return slug[:max_len] or "trip"


def _coerce_list(value) -> list[str]:
    """Accept list[str] or a single string; drop empties. Never fabricate."""
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value if str(v).strip()]


def _render_trip_md(payload: dict) -> str:
    destination = (payload.get("destination") or "Без направления").strip()
    start = (payload.get("start_date") or "").strip()
    end = (payload.get("end_date") or "").strip()
    purpose = (payload.get("purpose") or "").strip()
    area = (payload.get("area") or "").strip()
    status = (payload.get("status") or "planned").strip()
    agenda = _coerce_list(payload.get("agenda"))
    actions = _coerce_list(payload.get("action_items"))
    notes = (payload.get("notes") or "").strip()

    period = " → ".join(p for p in (start, end) if p) or "даты не указаны"

    lines = [f"# Поездка — {destination}", ""]
    lines.append(f"**Период:** {period}  ")
    if area:
        lines.append(f"**Направление:** {area}  ")
    lines.append(f"**Статус:** {status}  ")
    if purpose:
        lines.append(f"**Цель:** {purpose}")
    lines.append("")

    if agenda:
        lines.append("## План / встречи")
        lines.extend(f"- {a}" for a in agenda)
        lines.append("")

    if actions:
        lines.append("## Задачи")
        lines.extend(f"- [ ] {a}" for a in actions)
        lines.append("")

    if notes:
        lines.append("## Заметки")
        lines.append(notes)

    return "\n".join(lines).rstrip() + "\n"


def save(payload: dict) -> dict[str, object]:
    """Persist a trip plan to logs/trips/ + best-effort mirror to the Sheet."""
    destination = (payload.get("destination") or "").strip()
    if not destination:
        return {"error": "trip requires non-empty 'destination'"}

    # Defence-in-depth PII scan across the whole payload text.
    scan_text = " ".join(
        str(payload.get(f) or "") for f in ("destination", "purpose", "notes")
    )
    scan_text += " " + " ".join(
        _coerce_list(payload.get("agenda")) + _coerce_list(payload.get("action_items"))
    )
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

    trips_dir = _trips_dir()
    trips_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(destination)
    path = trips_dir / f"{date}-{slug}.md"
    if path.exists():
        i = 2
        while (trips_dir / f"{date}-{slug}-{i}.md").exists():
            i += 1
        path = trips_dir / f"{date}-{slug}-{i}.md"

    path.write_text(_render_trip_md(payload), encoding="utf-8")

    return {
        "saved_path": str(path),
        "destination": destination,
        "action_items_count": len(_coerce_list(payload.get("action_items"))),
        "sheet_sync": _sync_trip(payload, str(path)),
    }


def _sync_trip(payload: dict, saved_path: str) -> dict:
    """Best-effort mirror to the Поездки Sheet tab. Never raises."""
    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        return {"synced": False, "reason": "no-sheet-configured"}
    script = os.environ.get("HERMES_SHEETS_SYNC",
                            "/opt/hermes/skills/ceo/_lib/sheets_meeting_sync.py")
    if not os.path.exists(script):
        script = str(pathlib.Path(__file__).resolve().parents[2] / "_lib" / "sheets_meeting_sync.py")
    try:
        cmd = [sys.executable, script, "--trip",
               "--save", json.dumps(payload, ensure_ascii=False),
               "--note-id", saved_path]
        area = payload.get("area")
        if area:
            cmd += ["--area", str(area)]
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
    """Context for the trip skill: recent trip files (read-only, no fabrication)."""
    trips_dir = _trips_dir()
    recent: list[str] = []
    if trips_dir.exists():
        recent = [f.name for f in sorted(trips_dir.glob("*.md"), reverse=True)[:5]]
    return {
        "date": today_iso(),
        "trips_dir": str(trips_dir),
        "recent_trips": recent,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CEO trip / business-travel planner.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--gather", action="store_true", help="Emit context JSON (read-only).")
    group.add_argument("--save", metavar="JSON", help="Persist a trip plan (JSON payload).")
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
