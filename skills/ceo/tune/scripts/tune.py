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
import unicodedata

_REPO = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO))

_RULE_MAXLEN = 300

# Mirror the persona loader's injection screen so a rule we write can NEVER make
# load_soul_md() blank the WHOLE persona (self-DoS). Import the live patterns when
# available (stay in sync); fall back to a local copy for tests / offline.
try:  # pragma: no cover - import path varies by runtime
    from agent.prompt_builder import (  # type: ignore
        _CONTEXT_THREAT_PATTERNS as _LOADER_PATTERNS,
        _CONTEXT_INVISIBLE_CHARS as _LOADER_INVIS,
    )
    _INJECTION_PATTERNS = [p for p, _ in _LOADER_PATTERNS]
    _INVISIBLE_CHARS = set(_LOADER_INVIS)
except Exception:  # pragma: no cover
    _INJECTION_PATTERNS = [
        r'ignore\s+(previous|all|above|prior)\s+instructions',
        r'do\s+not\s+tell\s+the\s+user',
        r'system\s+prompt\s+override',
        r'disregard\s+(your|all|any)\s+(instructions|rules|guidelines)',
        r"act\s+as\s+(if|though)\s+you\s+(have\s+no|don't\s+have)\s+(restrictions|limits|rules)",
        r'<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->',
    ]
    _INVISIBLE_CHARS = {chr(c) for c in (
        0x200b, 0x200c, 0x200d, 0x2060, 0xfeff,
        0x202a, 0x202b, 0x202c, 0x202d, 0x202e,
    )}

# Deny-list: a self-tune rule must never be allowed to WEAKEN a hard safety control
# (privacy guard, send-confirmation, secret disclosure). Such intents are routed to
# the developer queue instead of silently rewriting the persona. RU + EN.
_SAFETY_DENYLIST = [
    # weaken send / action confirmation (RU): без подтверждения/проверки/согласования/
    # одобрения/разрешения/спроса
    r'без\s+(подтвержд|проверк|согласован|одобрен|разрешен|спрос)',
    r'не\s+(спрашива\w*|запрашива\w*|жди\w*|дожида\w*)\s+(подтвержд|разрешен|согласов|одобрен|спрос)',
    r'не\s+согласов\w*',
    r'(письм|email|событи|сообщени|календар|встреч|перевод|плат)\w*[^\n]{0,40}(без\s+подтвержд|без\s+согласов|сразу|автоматическ)',
    r'(отправля|создава|удаля|шли|переводи|плати)\w*[^\n]{0,40}(без\s+подтвержд|без\s+согласов|без\s+разрешен|сразу|автоматическ)',
    # disclose secrets (RU): показывай/выводи/присылай/сообщай/раскрывай … пароль/секрет/…
    r'(показыв|вывод|присыл|сообщ|раскрыв|дава|называ)\w*[^\n]{0,30}(парол|секрет|ключ|банк|pin|cvv|реквизит|токен)',
    # ignore / disable / hide guards (RU)
    r'игнорир\w*[^\n]{0,30}(privacy|приватн|guard|защит|правил|безопасн|ограничен)',
    r'не\s+показыв\w*[^\n]{0,20}(privacy|приватн|guard|защит|черновик)',
    r'(отключ|обход|сними|убери)\w*[^\n]{0,30}(privacy|приватн|guard|защит|ограничен|проверк|подтвержд)',
    # EN
    r'(disable|bypass|ignore|skip|turn\s+off|override)\b[^\n]{0,30}\b(guard|confirm|privacy|safety|rule|restriction|check)',
    r'always\s+send\b',
    r'without\s+(confirmation|asking|approval|permission)',
    r'(reveal|show|print|expose)\b[^\n]{0,30}(password|secret|api\s*key|token|bank)',
]


def _rule_is_unsafe(rule: str) -> "str | None":
    """Return a reason if the rule must NOT be written to the persona, else None.

    Two gates: (1) content that would trip the loader's injection screen and blank
    the whole persona; (2) rules whose intent is to disable a hard safety control.
    Text is NFKC-normalized so fullwidth / homoglyph / decomposed unicode can't slip
    a banned phrase past the patterns.
    """
    raw = rule or ""
    for ch in _INVISIBLE_CHARS:
        if ch in raw:
            return "invisible-unicode"
    norm = unicodedata.normalize("NFKC", " ".join(raw.split()))
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, norm, re.IGNORECASE):
            return "injection-pattern"
    for pat in _SAFETY_DENYLIST:
        if re.search(pat, norm, re.IGNORECASE):
            return "safety-sensitive"
    return None


CORR_HEADER = "## 🎛 Живые корректировки CEO (live, append-only — правила от Александра)"
CORR_INTRO = (
    "Правила ниже добавлены самим Александром через /tune. При конфликте они имеют\n"
    "ПРИОРИТЕТ над более ранними инструкциями — КРОМЕ жёстких правил безопасности\n"
    "(privacy guard; подтверждение отправки писем/событий; неразглашение паролей,\n"
    "банковских и медданных): эти правила через /tune переопределить НЕЛЬЗЯ."
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
    unsafe = _rule_is_unsafe(rule)
    if unsafe:
        # Refuse to write: would either blank the persona (injection scan) or
        # weaken a hard safety control. Caller routes it to human review instead.
        return {"applied": False, "reason": unsafe}
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
        # Best-effort mirror (the rule is already saved locally). Cap at 10s so a
        # slow/unhealthy Sheets API can't hang the user's /tune for 90 seconds.
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
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
        text = args.rule.strip()
        soul = append_rule_to_soul(text, date)
        applied = soul.get("applied", False)
        reason = soul.get("reason")
        # A rule refused for safety/injection reasons is NOT silently dropped — it
        # becomes a flagged item for human review (logged as "правило-отклонено").
        rejected_unsafe = (not applied and reason in (
            "safety-sensitive", "injection-pattern", "invisible-unicode"))
        kind = "правило-отклонено" if rejected_unsafe else "правило"
        result = {"kind": "правило", "applied": applied, "reason": reason, "soul": soul}
    else:
        if not args.bug.strip():
            print("ERROR: --bug cannot be empty.", file=sys.stderr)
            return 2
        kind, text = "баг", args.bug.strip()
        result = {"kind": kind, "applied": False, "soul": {"applied": False, "reason": "bug-not-applied"}}

    fid = _feedback_id("rule" if kind.startswith("правило") else "bug")
    result["feedback_id"] = fid
    result["log"] = log_feedback(kind, text, fid, now_iso)
    result["sheet_sync"] = mirror_to_sheet(kind, text, fid)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
