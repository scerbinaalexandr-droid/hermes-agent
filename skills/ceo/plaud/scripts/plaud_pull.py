#!/usr/bin/env python3
"""Pull new Plaud recordings and hand each one to the «scribe» worker.

Runs as a Hermes `no_agent` cron (every 30 min, no LLM on the poll):
    hermes cron create "*/30 * * * *" --script plaud_pull.py --no-agent \
        --name plaud_pull --deliver telegram

Flow: `plaud recent --days 2` → diff against ledger → for each new id with a
transcript: `plaud transcript`/`plaud summary` → raw/<id>/ → assignment on
the «Поручения» board for the scribe (owner's Telegram is subscribed to the
outcome) → ledger updated only after the card exists (idempotent, no dupes).

Paths (all on the volume, HERMES_HOME=/opt/data):
  .plaud/tokens.json   Plaud token — owner logs in on the Mac and copies it
                       here (chmod 600). Excluded from the backup. NEVER printed.
  plaud/seen.json      ledger of handled ids
  plaud/raw/<id>/      transcript.txt, summary.md
  logs/plaud.log       diagnostics (nothing technical goes to the chat)

Stdout is delivered verbatim to the owner: empty = silent run; on auth
failure one Russian line (throttled to once a day).
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ.get("HERMES_HOME", "/opt/data"))
AGENT_DIR = Path(os.environ.get("HERMES_AGENT_DIR", "/opt/hermes"))
LEDGER = HOME / "plaud" / "seen.json"
RAW = HOME / "plaud" / "raw"
LOG = HOME / "logs" / "plaud.log"
STATE = HOME / "plaud" / "state.json"
ASSIGN = AGENT_DIR / "skills" / "ceo" / "assign" / "scripts" / "assign.py"
DAYS = int(os.environ.get("PLAUD_PULL_DAYS", "2"))
MIN_SECONDS = int(os.environ.get("PLAUD_MIN_SECONDS", "60"))  # skip accidental taps
# Owner's rule (2026-09-18): only recordings made from this day on. Anything
# older is the archive — never fetched, never handed to the scribe.
SINCE = os.environ.get("PLAUD_SINCE", "2026-09-18")
AUTH_ALERT = "⚠️ Plaud отключился — нужно заново войти в Plaud на Mac и обновить ключ."


def log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")
    except OSError:
        pass


def plaud(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(HOME)  # → ~/.plaud/tokens.json lives on the volume
    return subprocess.run(["plaud", *args], capture_output=True, text=True, timeout=timeout, env=env)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# Real `plaud recent` line (CLI 2026-09):
#   of_be327e223ccc412ac372afd257feef7f  2026-07-11 00:23:56  2026-07-10  2h07m
_ROW_RE = re.compile(
    r"^\s*(of_[0-9a-f]{8,}|[A-Za-z0-9_-]{12,})\s+(\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?)"
    r"(?:\s+(\d{4}-\d{2}-\d{2}))?\s+(\S+)\s*$")
_ID_RE = re.compile(r"\b(?:id|ID)\W*([A-Za-z0-9_-]{6,})")
_FIELD_RE = re.compile(r"(id|name|created_at|duration)\s*[:=]\s*(.+?)(?=\s{2,}\w+\s*[:=]|\s*$)")
_HMS_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m(?:in)?)?(?:(\d+)s(?:ec)?)?$", re.I)


def parse_recent(text: str) -> list[dict]:
    """Best-effort parse of `plaud recent`: JSON if the CLI prints it, else
    one recording per line/block with an id, a name and a duration."""
    text = text.strip()
    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
            items = data if isinstance(data, list) else data.get("files") or data.get("items") or []
            return [{"id": str(i.get("id")), "name": i.get("name") or "", "created_at": i.get("created_at") or "",
                     "duration": _to_seconds(i.get("duration"))} for i in items if i.get("id")]
        except ValueError:
            pass
    out, seen = [], set()
    for line in text.splitlines():
        row = _ROW_RE.match(line)
        if row:
            rid, created, _day, dur = row.groups()
            if rid not in seen:
                seen.add(rid)
                out.append({"id": rid, "name": "", "created_at": created, "duration": _to_seconds(dur)})
            continue
        fields = {k: v.strip() for k, v in _FIELD_RE.findall(line)}
        rid = fields.get("id") or (_ID_RE.search(line).group(1) if _ID_RE.search(line) else None)
        if not rid or rid in seen:
            continue
        seen.add(rid)
        out.append({"id": rid, "name": fields.get("name", "")[:120], "created_at": fields.get("created_at", ""),
                    "duration": _to_seconds(fields.get("duration", ""))})
    return out


def _to_seconds(v) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    if not isinstance(v, str):
        return 0
    if v.strip().isdigit():
        return int(v.strip())
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", v.strip()):  # 1:05:00 or 25:30
        parts = [int(x) for x in v.strip().split(":")]
        return parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]
    m = _HMS_RE.match(v.strip().replace(" ", ""))
    if not m or not any(m.groups()):
        return 0
    h, mi, sec = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + sec


def alert_once(state: dict, key: str, text: str) -> None:
    now = int(time.time())
    if now - int(state.get(key, 0)) > 86400:
        print(text)
        state[key] = now
        save_json(STATE, state)


def main() -> int:
    state = load_json(STATE, {})
    seen = load_json(LEDGER, {})
    if not (HOME / ".plaud" / "tokens.json").exists():
        log("no token file")
        alert_once(state, "no_token", AUTH_ALERT)
        return 0

    try:
        r = plaud("recent", "--days", str(DAYS))
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log(f"recent failed: {type(exc).__name__}")
        return 0
    if r.returncode == 2:
        log("auth failed (exit 2)")
        alert_once(state, "auth", AUTH_ALERT)
        return 0
    if r.returncode != 0:
        log(f"recent exit {r.returncode}: {r.stderr.strip()[:200]}")
        return 0  # network/timeout: next tick retries

    handled = 0
    for rec in parse_recent(r.stdout):
        rid = rec["id"]
        if rid in seen:
            continue
        if rec.get("created_at") and rec["created_at"][:10] < SINCE:
            seen[rid] = {"skipped": "archive", "at": int(time.time())}
            continue
        if rec["duration"] and rec["duration"] < MIN_SECONDS:
            seen[rid] = {"skipped": "too_short", "at": int(time.time())}
            continue
        tr = plaud("transcript", rid, timeout=180)
        if tr.returncode != 0 or not tr.stdout.strip():
            log(f"{rid}: transcript not ready (exit {tr.returncode})")
            continue  # not in ledger → retried next tick
        sm = plaud("summary", rid, timeout=180)
        raw_dir = RAW / rid
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / "transcript.txt").write_text(tr.stdout, encoding="utf-8")
        if sm.returncode == 0 and sm.stdout.strip():
            (raw_dir / "summary.md").write_text(sm.stdout, encoding="utf-8")
        title = (rec["name"] or f"Запись от {rec.get('created_at') or rid}")[:80]
        brief = (
            f"Запись Plaud «{title}» ({rec.get('created_at') or 'дата в файле'}).\n"
            f"Транскрипт: {raw_dir / 'transcript.txt'}\n"
            f"Черновое резюме Plaud (если есть): {raw_dir / 'summary.md'}\n\n"
            "Определи тип записи: встреча/диктовка → протокол (резюме, решения, задачи, вопросы, "
            "цифры дословно); рассказ родных о семье → режим «летопись». Задачи перечисли списком — "
            "владелец подтвердит сам. В конце предложи метку блока PRJ-1…PRJ-7."
        )
        a = subprocess.run([sys.executable, str(ASSIGN), "--role", "scribe", "--board", "plaud",
                            "--title", title, "--brief", brief],
                           capture_output=True, text=True, timeout=60)
        try:
            res = json.loads(a.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            res = {"ok": False}
        if not res.get("ok"):
            log(f"{rid}: assign failed: {a.stdout.strip()[:200]} {a.stderr.strip()[:200]}")
            continue
        seen[rid] = {"task": res.get("id"), "at": int(time.time()), "title": title}
        save_json(LEDGER, seen)
        handled += 1
        log(f"{rid}: handed to scribe as {res.get('id')}")

    if handled:
        print(f"🎙 Новых записей Plaud: {handled}. Протоколист уже работает — итог пришлю.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never a traceback in the owner's chat
        log(f"crash: {type(exc).__name__}: {exc}")
        sys.exit(0)
