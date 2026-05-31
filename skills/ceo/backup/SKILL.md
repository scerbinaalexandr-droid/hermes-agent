---
name: backup
description: |
  Snapshot of the CEO OS memory layer (memory/, logs/daily/, logs/hooks/,
  config.yaml) to a PRIVATE GitHub repo. Daily via no_agent cron (03:00 UTC,
  zero LLM tokens) + manual /backup. INSTRUCTION_03 — Stage 7.
version: 1.0.0
author: alexandr.scerbina
license: MIT
metadata:
  hermes:
    tags: [ceo, backup, github, persistence]
    commands: [/backup]
    triggers:
      - "/backup"
      - "сделай бэкап"
      - "забэкапь память"
---

# /backup — Memory backup to private GitHub

Protects `memory/*` (irreplaceable: soul, decisions, projects, …) against
Railway Volume loss. Third protection layer: Mac (dev) + Railway Volume (prod)
+ GitHub (this backup).

## How it runs

- **Daily cron** — `no_agent` job at 03:00 UTC. The script IS the job (no LLM,
  zero tokens). Its stdout is delivered verbatim to Telegram.
- **Manual** — `/backup` for an on-demand snapshot.

The work is done by `scripts/backup.py` (stdlib only). On prod the entrypoint
copies it to `/opt/data/scripts/backup.py` (the only dir Hermes cron allows for
`--script`).

## What is backed up (whitelist)

`memory/` · `logs/daily/` (last 30 days) · `logs/hooks/` · `config.yaml`

## Never backed up

`.env`, any secrets/keys, `sessions/`, `__pycache__`, `*.pyc`, `*.tmp` — and the
GitHub token is scrubbed from every line of output.

## Required env (Railway Variables — never in code)

`BACKUP_GITHUB_TOKEN` (fine-grained PAT, Contents:write on the backup repo
only) · `BACKUP_REPO_URL` · `BACKUP_GIT_USER_NAME` · `BACKUP_GIT_USER_EMAIL`

## One-time cron setup (after env vars are live)

**Important:** `/cron` is NOT a Telegram slash-command. Cron jobs are created
either by asking the bot in natural language (so it invokes the internal
`cronjob` tool) OR via the Hermes CLI on the server. `--script` expects a path
RELATIVE to `~/.hermes/scripts/`, not absolute.

**Option A — through the bot (preferred):**

Send a plain-text message:
> Create cron job daily_memory_backup: run backup.py every day at 03:00 UTC,
> no-agent mode, deliver to telegram.

The bot will trigger the `cronjob` tool and return a real job_id. **Always
verify** — past bot fabricated job IDs (decisions.md 2026-05-24):
> show cron list

**Option B — via CLI (SSH/Railway shell):**
```
/opt/hermes/.venv/bin/hermes cron create "0 3 * * *" \
  --script backup.py --no-agent \
  --name daily_memory_backup --deliver telegram
```

## When the user types /backup manually

Run the script and report its stdout. Expected: `[backup] <ts> — snapshot pushed ✅`
or `no changes, nothing to push`. On failure, surface the (token-scrubbed) error.

## Security notes

- No conflict with the CEO OS guard hook: `no_agent` runs the script as a
  direct subprocess, bypassing the `pre_tool_call` tool layer — so its
  `git push` (to the backup repo) is not blocked.
- The script only READS `memory/` (the guard blocks WRITES) and pushes to a
  separate private repo, never the main `hermes-agent` repo.
