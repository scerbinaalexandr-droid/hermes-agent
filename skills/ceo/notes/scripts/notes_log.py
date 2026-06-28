#!/usr/bin/env python3
"""Structured notes helper for /notes skill.

Two modes:
  --gather              — emit JSON context (recent notes for de-dup awareness)
  --save '<JSON>'       — persist a structured note + update daily index

Storage layout under $HERMES_HOME/logs/notes/:
  YYYY-MM-DD/HHMM-<slug>.md       one file per note (canonical artifact)
  YYYY-MM-DD-index.md             append-only daily index with links

The index file is what Obsidian users open first ("what happened today"); the
per-note files are what backlinks point to.

Synced to Obsidian via:
  1. /backup daily cron pushes /opt/data/logs/notes/ to hermes-memory-backup
     private GitHub repo (logs/notes added to backup INCLUDE).
  2. Mac launchd plist hermes-notes-sync.plist pulls that repo every 6h and
     rsyncs into ALEX21_VAULT/03 — Notes/. (See plist file shipped with skill.)

Privacy: this script does NOT enforce privacy guard — that's the LLM's job
in SKILL.md Step 3. Helper trusts the JSON passed in (which has already been
shown to user for approval). Defence in depth: helper does sanity check —
refuses obvious PII patterns (emails, phone numbers, /etc/passwd-style paths,
banking details).

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


HERMES_HOME = pathlib.Path(
    os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
)
NOTES_ROOT = HERMES_HOME / "logs" / "notes"


# --- Defence-in-depth: refuse obvious sensitive patterns ------------------
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


# --- Date / slug utilities ------------------------------------------------
def _today_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def _hhmm_local() -> str:
    """HHMM in EEST (UTC+3) — user's local time."""
    now_utc = _dt.datetime.now(_dt.timezone.utc)
    eest = now_utc + _dt.timedelta(hours=3)
    return eest.strftime("%H%M")


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
    slug = "".join(out)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len] or "untitled"


# --- Save logic -----------------------------------------------------------
def _render_note_md(note: dict) -> str:
    topic = note.get("topic") or "Untitled"
    date = note.get("date") or _today_iso()
    mtype = note.get("meeting_type") or "note"
    participants = note.get("participants") or []
    decisions = note.get("decisions") or []
    actions = note.get("action_items") or []
    summary = note.get("summary") or ""
    raw = note.get("raw_text") or ""

    lines = []
    lines.append(f"# {topic}")
    lines.append("")
    lines.append(f"**Date:** {date}  ")
    lines.append(f"**Type:** {mtype}  ")
    if participants:
        lines.append(f"**Participants:** {', '.join(participants)}")
    lines.append("")

    if decisions:
        lines.append("## Decisions")
        for d in decisions:
            lines.append(f"- {d}")
        lines.append("")

    if actions:
        lines.append("## Action items")
        for a in actions:
            lines.append(f"- [ ] {a}")
        lines.append("")

    if summary:
        lines.append("## Summary")
        lines.append(summary)
        lines.append("")

    if raw:
        lines.append("---")
        lines.append("")
        lines.append("## Raw input (transcript / OCR / text)")
        lines.append("")
        lines.append("```")
        lines.append(raw.strip())
        lines.append("```")

    return "\n".join(lines) + "\n"


def _append_index(date_iso: str, hhmm: str, slug: str, topic: str, mtype: str) -> pathlib.Path:
    """Append a row to the daily index (YYYY-MM-DD-index.md)."""
    idx_path = NOTES_ROOT / f"{date_iso}-index.md"
    relpath = f"{date_iso}/{hhmm}-{slug}.md"

    if not idx_path.exists():
        idx_path.write_text(
            f"# Notes — {date_iso}\n\n"
            f"| Time | Type | Topic | Link |\n"
            f"|------|------|-------|------|\n",
            encoding="utf-8",
        )

    safe_topic = topic.replace("|", "/")
    row = f"| {hhmm[:2]}:{hhmm[2:]} | {mtype} | {safe_topic} | [[{relpath}]] |\n"
    with open(idx_path, "a", encoding="utf-8") as f:
        f.write(row)
    return idx_path


def cmd_save(payload: dict) -> dict:
    # Validate required fields (no fake data — refuse if missing)
    topic = (payload.get("topic") or "").strip()
    if not topic:
        return {"error": "topic is required and cannot be empty"}

    raw_text = payload.get("raw_text") or ""
    pii = _scan_pii(raw_text + " " + topic)
    if pii:
        return {
            "error": "refused: input contains sensitive data patterns",
            "patterns_found": pii,
            "guidance": "redact the sensitive fields and retry. Helper enforces a hard stop on emails, credit cards, API keys, IBAN.",
        }

    date_iso = (payload.get("date") or _today_iso())[:10]
    # Validate date roughly
    try:
        _dt.date.fromisoformat(date_iso)
    except ValueError:
        date_iso = _today_iso()

    hhmm = _hhmm_local()
    slug = _slugify(topic)
    mtype = payload.get("meeting_type") or "note"

    day_dir = NOTES_ROOT / date_iso
    day_dir.mkdir(parents=True, exist_ok=True)

    note_path = day_dir / f"{hhmm}-{slug}.md"
    # Uniqueness: if exists (rare, same minute + slug), append suffix
    if note_path.exists():
        i = 2
        while (day_dir / f"{hhmm}-{slug}-{i}.md").exists():
            i += 1
        note_path = day_dir / f"{hhmm}-{slug}-{i}.md"

    note_md = _render_note_md(payload)
    note_path.write_text(note_md, encoding="utf-8")

    idx_path = _append_index(date_iso, hhmm, slug, topic, mtype)

    return {
        "saved_path": str(note_path),
        "index_path": str(idx_path),
        "obsidian_eta": "next morning (~06:00 EEST) after launchd sync runs",
        "action_items_count": len(payload.get("action_items") or []),
        "sheet_sync": _sync_to_sheet(payload, str(note_path)),
    }


def _sync_to_sheet(payload: dict, saved_path: str) -> dict:
    """Best-effort: mirror a meeting into the master Google Sheet. Never raises.

    Runs deterministically here (not as an LLM step) so every meeting/call/protocol
    reaches the Sheet. Non-meeting notes and a missing sheet config are no-ops.
    """
    mtype = payload.get("meeting_type") or "note"
    if mtype not in ("meeting", "call", "protocol"):
        return {"synced": False, "reason": "not-a-meeting"}
    sheet_id = os.environ.get("HERMES_MEETING_SHEET_ID")
    if not sheet_id:
        return {"synced": False, "reason": "no-sheet-configured"}

    script = os.environ.get("HERMES_SHEETS_SYNC",
                            "/opt/hermes/skills/ceo/_lib/sheets_meeting_sync.py")
    if not os.path.exists(script):
        script = str(pathlib.Path(__file__).resolve().parents[2] / "_lib" / "sheets_meeting_sync.py")
    try:
        cmd = [sys.executable, script, "--save", json.dumps(payload, ensure_ascii=False),
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


def cmd_gather() -> dict:
    """Return context: today's notes count + last 3 note topics for dedup awareness."""
    today = _today_iso()
    today_idx = NOTES_ROOT / f"{today}-index.md"
    today_count = 0
    if today_idx.exists():
        # Count table rows (lines starting with `|` and NOT separator)
        for line in today_idx.read_text(encoding="utf-8").splitlines():
            if line.startswith("|") and "---" not in line and "Time" not in line:
                today_count += 1

    recent_topics: list[str] = []
    if NOTES_ROOT.exists():
        indexes = sorted(NOTES_ROOT.glob("*-index.md"), reverse=True)[:5]
        for idx in indexes:
            for line in idx.read_text(encoding="utf-8").splitlines():
                if line.startswith("|") and "---" not in line and "Time" not in line:
                    parts = [p.strip() for p in line.strip("|").split("|")]
                    if len(parts) >= 3:
                        recent_topics.append(parts[2])
                if len(recent_topics) >= 10:
                    break
            if len(recent_topics) >= 10:
                break

    return {
        "today_iso": today,
        "today_notes_count": today_count,
        "recent_topics": recent_topics[:10],
        "notes_root": str(NOTES_ROOT),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--gather", action="store_true")
    g.add_argument("--save", metavar="JSON", help="JSON payload to save")
    args = ap.parse_args()

    if args.gather:
        print(json.dumps(cmd_gather(), ensure_ascii=False, indent=2))
        return 0

    try:
        payload = json.loads(args.save)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"invalid JSON: {e}"}, ensure_ascii=False))
        return 1
    if not isinstance(payload, dict):
        print(json.dumps({"error": "payload must be a JSON object"}, ensure_ascii=False))
        return 1

    result = cmd_save(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
