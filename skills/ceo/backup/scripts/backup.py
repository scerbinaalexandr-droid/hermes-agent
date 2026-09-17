#!/usr/bin/env python3
"""Daily backup of Hermes CEO memory + logs to a private GitHub repo.

Designed to run as a Hermes `no_agent` cron job (direct subprocess, NO LLM):
    hermes cron create "0 3 * * *" \
        --script /opt/data/scripts/backup.py --no-agent \
        --name daily_memory_backup --deliver telegram

Because no_agent delivers the script's stdout VERBATIM (e.g. to Telegram), this
script must NEVER print the GitHub token — every subprocess output is run
through scrub() before being surfaced.

Env (set in Railway Variables, never in code/config):
    BACKUP_GITHUB_TOKEN    fine-grained PAT, Contents:write on the backup repo only
    BACKUP_REPO_URL        https://github.com/<owner>/hermes-memory-backup.git
    BACKUP_GIT_USER_NAME   commit author name
    BACKUP_GIT_USER_EMAIL  commit author email
    HERMES_HOME            /opt/data (default)

Stdlib only — no external deps (runs under the plain cron python).
"""
import gzip
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/opt/data"))
REPO_URL = (os.environ.get("BACKUP_REPO_URL") or "").strip()
TOKEN = (os.environ.get("BACKUP_GITHUB_TOKEN") or "").strip()
GIT_USER = (os.environ.get("BACKUP_GIT_USER_NAME") or "Hermes Backup").strip()
GIT_EMAIL = (os.environ.get("BACKUP_GIT_USER_EMAIL") or "hermes@noreply.local").strip()

# What to back up (whitelist, relative to HERMES_HOME).
INCLUDE = ["memory", "memories", "SOUL.md", "cron/jobs.json", "kanban/boards", "plaud",
           "logs/daily", "logs/coaching", "logs/hooks", "logs/telemetry",
           "logs/notes", "logs/diary", "logs/trips", "logs/curator", "config.yaml"]
# Never copy these, even if matched by INCLUDE (defence-in-depth — .env etc.).
# Live SQLite files are in here too: a byte copy taken while the app is writing
# is a corrupt database. Every database we keep goes through snapshot_sqlite().
EXCLUDE = (".env", "*.pyc", "__pycache__", "sessions", "*.tmp", "*.key", "*.pem", ".plaud", "tokens.json",
           "google_token.json", "google_client_secret.json", "google_*.json",
           "*.db", "*.db-wal", "*.db-shm", "*.sqlite", "*.sqlite3")
# Retention: keep only the most recent N dated daily logs in the backup.
LOGS_DAILY_KEEP = 30
# Chat-history shards younger than this are rewritten on every run (a day is
# only final once it is past); older shards are written once and never touched.
CHAT_REWRITE_DAYS = 3

# Credentials must never reach the backup repo, not even inside a chat message
# the CEO once pasted. Applied to every exported row.
SECRET_RE = re.compile(
    r"sk-ant-[A-Za-z0-9_-]{12,}|sk-or-[A-Za-z0-9_-]{12,}|sk-proj-[A-Za-z0-9_-]{12,}"
    r"|gsk_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|AIza[A-Za-z0-9_-]{20,}|[0-9]{9,10}:AA[A-Za-z0-9_-]{30,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)


def scrub(text: str) -> str:
    """Remove the token from any text before it can be printed/delivered."""
    if TOKEN and text:
        return text.replace(TOKEN, "***TOKEN***")
    return text or ""


FAIL_MSG = "⚠️ Копия памяти сегодня не сохранилась — нужна проверка."
FAIL_LOG = HERMES_HOME / "logs" / "backup.log"


def log_detail(detail: str) -> None:
    """Diagnostics go to a file on the volume, never to stdout (= the chat)."""
    try:
        FAIL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FAIL_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(timezone.utc).isoformat()} {scrub(detail)}\n")
    except OSError:
        pass  # best-effort; the owner-facing alert does not depend on it


def fail(detail: str) -> int:
    """Alert the owner cleanly; keep the reason in the log file.

    Exits 0 on purpose: a non-zero exit makes the cron scheduler wrap stdout in
    a technical "Cron watchdog … script failed / exited with code 1" envelope,
    which is exactly the service noise the owner must not see.
    """
    log_detail(detail)
    print(FAIL_MSG)
    return 0


def run(cmd, cwd=None, check=True, timeout=180):
    # Bound every git call: an unreachable GitHub / slow DNS must not hang the
    # cron slot forever (which would silently freeze the whole backup job).
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(scrub(f"`{' '.join(cmd)}` timed out after {timeout}s (network?)"))
    if check and r.returncode != 0:
        raise RuntimeError(scrub(f"`{' '.join(cmd)}` failed: {r.stderr.strip()}"))
    return r


def ssh_key_path() -> Optional[Path]:
    """Deploy key for the backup repo, if one was provisioned.

    Preferred over BACKUP_GITHUB_TOKEN: a personal access token expires (this
    one did, silently, and offsite backups stopped for 11 days), while a deploy
    key does not and is scoped to this single repository.
    """
    p = Path(os.environ.get("BACKUP_SSH_KEY") or (HERMES_HOME / ".ssh" / "backup_key"))
    return p if p.is_file() else None


def ssh_url() -> Optional[str]:
    """Rewrite the configured https remote to its SSH form."""
    m = re.match(r"^https://github\.com/([^/]+)/(.+?)(?:\.git)?/?$", REPO_URL)
    return f"git@github.com:{m.group(1)}/{m.group(2)}.git" if m else None


def apply_git_env() -> None:
    """Pin the deploy key for every git call in this process."""
    key = ssh_key_path()
    if key:
        os.environ["GIT_SSH_COMMAND"] = (
            f"ssh -i {key} -o IdentitiesOnly=yes "
            "-o StrictHostKeyChecking=accept-new -o BatchMode=yes"
        )
    os.environ["GIT_TERMINAL_PROMPT"] = "0"  # never block the cron slot on a prompt


def auth_url() -> str:
    """Remote URL to use: SSH deploy key first, token as fallback."""
    if ssh_key_path():
        url = ssh_url()
        if url:
            return url
    if TOKEN and REPO_URL.startswith("https://"):
        return REPO_URL.replace("https://", f"https://x-access-token:{TOKEN}@", 1)
    return REPO_URL  # local file:// (tests) or already-auth'd


def rotate_daily_logs(staging: Path) -> None:
    daily = staging / "logs" / "daily"
    if not daily.exists():
        return
    files = sorted(daily.glob("*.md"))
    for old in files[:-LOGS_DAILY_KEEP] if len(files) > LOGS_DAILY_KEEP else []:
        old.unlink()


def redact(text: str) -> str:
    return SECRET_RE.sub("***REDACTED***", text)


def gzip_writer(path: Path):
    """Deterministic gzip: no mtime, no embedded filename.

    Both would change the compressed bytes on every run even when the content
    is identical, which would push an empty "snapshot" commit every night.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fobj = open(path, "wb")
    return gzip.GzipFile(fileobj=fobj, mode="wb", compresslevel=9, mtime=0)


def snapshot_sqlite(src: Path, dst_gz: Path) -> bool:
    """Consistent read-only snapshot of a live SQLite database, gzipped.

    Read-only matters beyond correctness: this script runs as a cron job, and a
    read-write connection can create WAL/SHM files owned by the wrong user —
    exactly what took the container down on 2026-06-30.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="hermes-sqlite-"))
    try:
        con = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
        try:
            con.execute("VACUUM INTO ?", (str(tmpdir / "snap.db"),))
        finally:
            con.close()
        with open(tmpdir / "snap.db", "rb") as fh, gzip_writer(dst_gz) as out:
            shutil.copyfileobj(fh, out)
        return True
    except Exception as exc:
        log_detail(f"sqlite snapshot failed for {src.name}: {exc}")
        return False
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def backup_kanban(staging: Path) -> int:
    """Kanban boards carry the CEO's tasks since 2026-08-16 and live only here."""
    sources = []
    root_db = HERMES_HOME / "kanban.db"
    if root_db.is_file():
        sources.append((root_db, "_root.db.gz"))
    boards = HERMES_HOME / "kanban" / "boards"
    if boards.is_dir():
        for db in sorted(boards.glob("*/kanban.db")):
            sources.append((db, f"{db.parent.name}.db.gz"))
    return sum(snapshot_sqlite(src, staging / "state" / "kanban" / name)
               for src, name in sources)


def export_chat_history(staging: Path) -> int:
    """Chat history as day-sharded JSONL — not the raw 171 MB database file.

    Two reasons for the shape. The full-text search indexes are most of that
    size and SQLite rebuilds them from the rows, so they are not worth storing.
    And git keeps every version of every file forever: one growing export
    rewritten nightly would add its whole size to the repo each night, which no
    retention policy can undo. A finished day is written once and never changes,
    so the repo grows by about a day of conversation.
    """
    src = HERMES_HOME / "state.db"
    if not src.is_file():
        return 0
    written = 0
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        today = datetime.now(timezone.utc).date()
        recent = {(today - timedelta(days=i)).isoformat() for i in range(CHAT_REWRITE_DAYS)}
        for table, ts_col in (("messages", "timestamp"), ("sessions", "started_at")):
            day_dir = staging / "state" / table
            have = {p.name[:-len(".jsonl.gz")] for p in day_dir.glob("*.jsonl.gz")} \
                if day_dir.is_dir() else set()
            days = [r[0] for r in con.execute(
                f"SELECT DISTINCT date({ts_col}, 'unixepoch') FROM {table} "
                f"WHERE {ts_col} IS NOT NULL ORDER BY 1")]
            for day in days:
                if day in have and day not in recent:
                    continue
                rows = con.execute(
                    f"SELECT * FROM {table} WHERE date({ts_col}, 'unixepoch') = ? "
                    f"ORDER BY rowid", (day,))
                with gzip_writer(day_dir / f"{day}.jsonl.gz") as raw, \
                        io.TextIOWrapper(raw, encoding="utf-8") as fh:
                    for row in rows:
                        fh.write(redact(json.dumps(dict(row), ensure_ascii=False,
                                                   default=str)) + "\n")
                written += 1
        # Small enough to rewrite whole; it is per-session billing, not content.
        with gzip_writer(staging / "state" / "session_model_usage.jsonl.gz") as raw, \
                io.TextIOWrapper(raw, encoding="utf-8") as fh:
            for row in con.execute("SELECT * FROM session_model_usage ORDER BY rowid"):
                fh.write(json.dumps(dict(row), ensure_ascii=False, default=str) + "\n")
        written += 1
    finally:
        con.close()
    return written


def copy_includes(staging: Path) -> None:
    for item in INCLUDE:
        src = HERMES_HOME / item
        dst = staging / item
        if not src.exists():
            continue
        # Wipe the previous copy so deletions on prod propagate to the backup.
        if dst.is_dir():
            shutil.rmtree(dst)
        elif dst.exists():
            dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*EXCLUDE))
        else:
            if any(src.match(p) or p in src.name for p in EXCLUDE):
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def main() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # A deploy key alone is enough — the token became optional once the PAT
    # expired and took the offsite backup down with it.
    if not REPO_URL or not (TOKEN or ssh_key_path()):
        return fail("BACKUP_REPO_URL unset or no credential (deploy key / token)")
    apply_git_env()

    with tempfile.TemporaryDirectory(prefix="hermes-backup-") as tmp:
        staging = Path(tmp) / "repo"
        # 1. Clone the private repo (shallow). First-ever run may have an empty repo.
        clone = run(["git", "clone", "--depth=1", auth_url(), str(staging)], check=False)
        if clone.returncode != 0:
            staging.mkdir(parents=True, exist_ok=True)
            run(["git", "init"], cwd=staging)
            run(["git", "checkout", "-b", "main"], cwd=staging, check=False)
            # A failed clone can still leave `origin` configured — use set-url
            # in that case so we don't crash on "remote origin already exists".
            existing = run(["git", "remote"], cwd=staging, check=False)
            if "origin" in (existing.stdout or "").split():
                run(["git", "remote", "set-url", "origin", auth_url()], cwd=staging)
            else:
                run(["git", "remote", "add", "origin", auth_url()], cwd=staging)

        run(["git", "config", "user.name", GIT_USER], cwd=staging)
        run(["git", "config", "user.email", GIT_EMAIL], cwd=staging)

        # 2. Refresh content + rotate + write README.
        copy_includes(staging)
        rotate_daily_logs(staging)
        # Live databases: consistent snapshots, never raw file copies.
        backup_kanban(staging)
        export_chat_history(staging)
        (staging / "README.md").write_text(
            "# Hermes Memory Backup\n\n"
            f"**Last snapshot:** {ts}\n\n"
            "**Source:** Railway production (HERMES_HOME=/opt/data)\n\n"
            "**Privacy:** PRIVATE. Contains business directions data + personal context. "
            "Do not share, do not make public, do not fork.\n",
            encoding="utf-8",
        )

        # 3. Commit only if something changed.
        run(["git", "add", "-A"], cwd=staging)
        status = run(["git", "status", "--porcelain"], cwd=staging, check=False)
        if not status.stdout.strip():
            # Nothing changed — stay silent, the owner gets no service noise.
            return 0

        run(["git", "commit", "-m", f"snapshot: {ts}"], cwd=staging)
        push = run(["git", "push", "origin", "HEAD:main"], cwd=staging, check=False)
        if push.returncode != 0:
            return fail(f"push failed: {push.stderr.strip()}")

    # Success is silent by design: a daily "ok" is noise. Failures speak up.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never leak token in a traceback
        sys.exit(fail(f"{type(exc).__name__}: {exc}"))
