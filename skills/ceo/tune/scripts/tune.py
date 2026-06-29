"""Tune helper — CEO feedback / self-adjustment channel via Telegram.

Two safe, bounded modes (the LLM classifies, the user approves a draft first):

  --rule "<text>"   Behavioral preference (tone / format / default). Appended as a
                    single capped bullet to the live-corrections section of the
                    persona (/opt/data/SOUL.md), so it takes effect next message.
                    APPEND-ONLY to one delimited section; never rewrites SOUL.

  --bug "<text>"    A code/behaviour defect for the developer (Claude) to fix.
                    Logged to the dev-feedback queue; does NOT touch the persona.

Both modes mirror to the CEO's Sheet ("Корректировки" tab) and to a local
feedback log, so there is an audit trail of every adjustment. Never raises on
the Sheet/log side (best-effort); returns JSON describing what happened.

Usage:
  python tune.py --rule "пиши короче, без воды"
  python tune.py --bug  "после /capture кнопки не появились, только текст"
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

_RULE_MAXLEN = 300

CORR_HEADER = "## 🎛 Живые корректировки CEO (live, append-only — правила от Александра)"
CORR_INTRO = (
    "Правила ниже добавлены самим Александром через /tune. Они имеют ПРИОРИТЕТ над\n"
    "более ранними инструкциями при конфликте. Применяй их всегда."
)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _feedback_id(kind: str) -> str:
    n = _now()
    return f"fb/{n.strftime('%Y-%m-%d')}/{n.strftime('%H%M%S')}-{kind}"


def _soul_path() -> pathlib.Path:
    home = os.environ.get("HERMES_HOME", "/opt/data")
    return pathlib.Path(os.environ.get("HERMES_SOUL_PATH", os.path.join(home, "SOUL.md")))


def append_rule_to_soul(rule: str, date: str) -> dict:
    """Append a single bounded behavioral rule to the persona's live-corrections
    section. Creates the section once if absent. Append-only; never edits other
    content. Returns {applied, path} or {applied:False, reason}.
    """
    rule = " ".join((rule or "").split())[:_RULE_MAXLEN].strip()
    if not rule:
        return {"applied": False, "reason": "empty-rule"}
    path = _soul_path()
    if not path.exists():
        return {"applied": False, "reason": f"soul-missing:{path}"}
    bullet = f"- [{date}] {rule}"
    text = path.read_text(encoding="utf-8")
    if CORR_HEADER not in text:
        text = text.rstrip() + f"\n\n{CORR_HEADER}\n\n{CORR_INTRO}\n\n{bullet}\n"
    else:
        # Insert the bullet right after the header line (keeps newest near top of
        # the section, never disturbs the rest of the file).
        pat = re.compile(rf"({re.escape(CORR_HEADER)}[ \t]*\n)", flags=re.MULTILINE)
        text = pat.sub(lambda m: m.group(1) + bullet + "\n", text, count=1)
    path.write_text(text, encoding="utf-8")
    return {"applied": True, "path": str(path)}


def _feedback_log_path() -> pathlib.Path:
    home = os.environ.get("HERMES_HOME", "/opt/data")
    return pathlib.Path(home) / "logs" / "feedback.md"


def log_feedback(kind: str, text: str, fid: str, now_iso: str) -> dict:
    """Best-effort append to the dev-feedback log. Never raises."""
    try:
        p = _feedback_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"- {now_iso} [{kind}] ({fid}) {text}\n")
        return {"logged": True, "path": str(p)}
    except Exception as exc:
        return {"logged": False, "reason": str(exc)[:200]}


def mirror_to_sheet(kind: str, text: str, fid: str) -> dict:
    """Best-effort mirror to the Корректировки tab. Never raises. No-op if no sheet."""
    if not os.environ.get("HERMES_MEETING_SHEET_ID"):
        return {"synced": False, "reason": "no-sheet-configured"}
    script = os.environ.get("HERMES_SHEETS_SYNC",
                            "/opt/hermes/skills/ceo/_lib/sheets_meeting_sync.py")
    if not os.path.exists(script):
        script = str(_REPO / "skills" / "ceo" / "_lib" / "sheets_meeting_sync.py")
    payload = {"kind": kind, "text": text}
    try:
        cmd = [sys.executable, script, "--feedback",
               "--save", json.dumps(payload, ensure_ascii=False), "--note-id", fid]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if r.returncode == 0:
            try:
                return {"synced": True, **json.loads((r.stdout or "").strip() or "{}")}
            except Exception:
                return {"synced": True, "raw": (r.stdout or "").strip()[:200]}
        return {"synced": False, "reason": ((r.stdout or "") + (r.stderr or "")).strip()[:200]}
    except Exception as exc:
        return {"synced": False, "reason": str(exc)[:200]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--rule", metavar="TEXT", help="Behavioral rule → persona (self-tune).")
    g.add_argument("--bug", metavar="TEXT", help="Code/behaviour defect → developer queue.")
    args = ap.parse_args()

    now = _now()
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    date = now.strftime("%Y-%m-%d")

    if args.rule is not None:
        if not args.rule.strip():
            print("ERROR: --rule cannot be empty.", file=sys.stderr)
            return 2
        kind, text = "правило", args.rule.strip()
        soul = append_rule_to_soul(text, date)
        result = {"kind": kind, "applied": soul.get("applied", False), "soul": soul}
    else:
        if not args.bug.strip():
            print("ERROR: --bug cannot be empty.", file=sys.stderr)
            return 2
        kind, text = "баг", args.bug.strip()
        result = {"kind": kind, "applied": False, "soul": {"applied": False, "reason": "bug-not-applied"}}

    fid = _feedback_id("rule" if kind == "правило" else "bug")
    result["feedback_id"] = fid
    result["log"] = log_feedback(kind, text, fid, now_iso)
    result["sheet_sync"] = mirror_to_sheet(kind, text, fid)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
