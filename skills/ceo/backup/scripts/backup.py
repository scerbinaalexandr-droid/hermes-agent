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
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/opt/data"))
REPO_URL = (os.environ.get("BACKUP_REPO_URL") or "").strip()
TOKEN = (os.environ.get("BACKUP_GITHUB_TOKEN") or "").strip()
GIT_USER = (os.environ.get("BACKUP_GIT_USER_NAME") or "Hermes Backup").strip()
GIT_EMAIL = (os.environ.get("BACKUP_GIT_USER_EMAIL") or "hermes@noreply.local").strip()

# What to back up (whitelist, relative to HERMES_HOME).
INCLUDE = ["memory", "logs/daily", "logs/coaching", "logs/hooks", "logs/telemetry", "logs/notes", "logs/diary", "config.yaml"]
# Never copy these, even if matched by INCLUDE (defence-in-depth — .env etc.).
EXCLUDE = (".env", "*.pyc", "__pycache__", "sessions", "*.tmp", "*.key", "*.pem")
# Retention: keep only the most recent N dated daily logs in the backup.
LOGS_DAILY_KEEP = 30


def scrub(text: str) -> str:
    """Remove the token from any text before it can be printed/delivered."""
    if TOKEN and text:
        return text.replace(TOKEN, "***TOKEN***")
    return text or ""


def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(scrub(f"`{' '.join(cmd)}` failed: {r.stderr.strip()}"))
    return r


def auth_url() -> str:
    """Inject the token as HTTP basic-auth user (scrubbed from all output)."""
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
    if not REPO_URL or not TOKEN:
        print("[backup] SKIP — BACKUP_REPO_URL / BACKUP_GITHUB_TOKEN not set")
        return 0

    with tempfile.TemporaryDirectory(prefix="hermes-backup-") as tmp:
        staging = Path(tmp) / "repo"
        # 1. Clone the private repo (shallow). First-ever run may have an empty repo.
        clone = run(["git", "clone", "--depth=1", auth_url(), str(staging)], check=False)
        if clone.returncode != 0:
            staging.mkdir(parents=True, exist_ok=True)
            run(["git", "init"], cwd=staging)
            run(["git", "checkout", "-b", "main"], cwd=staging, check=False)
            run(["git", "remote", "add", "origin", auth_url()], cwd=staging)

        run(["git", "config", "user.name", GIT_USER], cwd=staging)
        run(["git", "config", "user.email", GIT_EMAIL], cwd=staging)

        # 2. Refresh content + rotate + write README.
        copy_includes(staging)
        rotate_daily_logs(staging)
        (staging / "README.md").write_text(
            "# Hermes Memory Backup\n\n"
            f"**Last snapshot:** {ts}\n\n"
            "**Source:** Railway production (HERMES_HOME=/opt/data)\n\n"
            "**Privacy:** PRIVATE. Contains TANDEM business data + personal context. "
            "Do not share, do not make public, do not fork.\n",
            encoding="utf-8",
        )

        # 3. Commit only if something changed.
        run(["git", "add", "-A"], cwd=staging)
        status = run(["git", "status", "--porcelain"], cwd=staging, check=False)
        if not status.stdout.strip():
            print(f"[backup] {ts} — no changes, nothing to push")
            return 0

        run(["git", "commit", "-m", f"snapshot: {ts}"], cwd=staging)
        push = run(["git", "push", "origin", "HEAD:main"], cwd=staging, check=False)
        if push.returncode != 0:
            print(scrub(f"[backup] {ts} — PUSH FAILED: {push.stderr.strip()}"))
            return 1

    print(f"[backup] {ts} — snapshot pushed ✅")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never leak token in a traceback
        print(scrub(f"[backup] ERROR: {exc}"))
        sys.exit(1)
