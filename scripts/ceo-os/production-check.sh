#!/usr/bin/env bash
# Production runtime debug for "/<cmd> → Unknown command" symptoms.
#
# Run on the host where the Hermes Telegram bot actually answers.
# Read-only. Does not modify anything. Outputs everything maintainers need
# to identify the live process, runtime config, and CEO skill visibility.
#
# Usage:
#   bash scripts/ceo-os/production-check.sh
#
# Expected output sections: (1) process & container inventory,
# (2) HERMES_HOME and config.yaml status, (3) runtime external_dirs as the
# live Python interpreter sees them, (4) skill scan trace, (5) Telegram
# BotCommands cache, (6) verdict.

set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
echo "Repo root: $REPO_ROOT"
echo "Now: $(date -u +%FT%TZ)"
echo

# --- 1. Process & container inventory ---------------------------------------
echo "================================================================"
echo "1. PROCESS & CONTAINER INVENTORY"
echo "================================================================"

echo "--- 1a. docker containers running ---"
if command -v docker >/dev/null 2>&1; then
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Command}}' 2>&1 | head -30
  echo
  echo "--- 1b. compose project (if running here) ---"
  docker compose ls 2>&1 | head -5
  echo
  echo "--- 1c. hermes container details ---"
  CID="$(docker ps -q --filter 'name=hermes' --filter 'ancestor=hermes-agent' 2>/dev/null | head -1)"
  if [ -n "$CID" ]; then
    docker inspect "$CID" --format '
container: {{.Name}}
image: {{.Config.Image}}
state: {{.State.Status}}
started: {{.State.StartedAt}}
restart count: {{.RestartCount}}
working dir: {{.Config.WorkingDir}}
cmd: {{json .Config.Cmd}}
entrypoint: {{json .Config.Entrypoint}}
volumes:
{{range .Mounts}}  - {{.Source}} -> {{.Destination}} ({{.Mode}}){{println}}{{end}}
env keys (values redacted):
{{range .Config.Env}}{{if (or (hasPrefix . "HERMES") (hasPrefix . "TELEGRAM"))}}  - {{.}}{{println}}{{end}}{{end}}
' 2>&1 \
      | sed -E 's/(TOKEN|KEY|SECRET|PASSWORD|API_KEY)=[^[:space:]]+/\1=<REDACTED>/g'
    echo "HERMES_PROD_CID=$CID"
  else
    echo "(no container matched 'hermes')"
  fi
else
  echo "(docker CLI not available)"
fi

echo
echo "--- 1d. host process list (filtered, IDE/editor noise stripped) ---"
# Show only PID + truncated short command (first 80 chars). Never dump full
# command line — env vars can leak via ps on macOS/Linux when a parent
# process injected them into argv (Cursor, VS Code do this).
ps -eo pid,ppid,user,etime,comm 2>/dev/null \
  | awk 'NR==1 || ($NF ~ /[Pp]ython|hermes|tini/)' \
  | grep -v -iE 'cursor|vscode|code helper|electron|extension-host|pylsp|pysemgrep|http\.server|serve_dashboard' \
  | head -20

# Additionally — only Hermes-like Python commands, again truncated.
echo
echo "--- 1d-extra. python procs whose args reference cli.py / gateway ---"
ps -eo pid,etime,args 2>/dev/null \
  | awk '$0 ~ /cli\.py|hermes_cli|gateway/ && $0 !~ /production-check|production-fix|grep/' \
  | sed -E 's/(TOKEN|KEY|SECRET|PASSWORD)=[^[:space:]]+/\1=<REDACTED>/g' \
  | cut -c1-200 \
  | head -10

echo
echo "--- 1e. systemd services ---"
if command -v systemctl >/dev/null 2>&1; then
  systemctl list-units --type=service --no-pager 2>/dev/null | grep -i hermes | head -5 || echo "(no hermes systemd unit)"
fi

# --- 2. HERMES_HOME & config.yaml -------------------------------------------
echo
echo "================================================================"
echo "2. HERMES_HOME & CONFIG"
echo "================================================================"

HOST_HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
echo "Host HERMES_HOME env: ${HERMES_HOME:-<unset, will default to ~/.hermes>}"
echo "Resolved host HERMES_HOME: $HOST_HERMES_HOME"
echo "config.yaml on host: $HOST_HERMES_HOME/config.yaml"
if [ -f "$HOST_HERMES_HOME/config.yaml" ]; then
  echo "--- host config.yaml content ---"
  cat "$HOST_HERMES_HOME/config.yaml"
else
  echo "(host config.yaml ABSENT — fix needed)"
fi
echo
echo "Host skills dir: $HOST_HERMES_HOME/skills"
ls -la "$HOST_HERMES_HOME/skills" 2>&1 | head -10

# --- 3. Runtime view (inside container or host venv) ------------------------
echo
echo "================================================================"
echo "3. RUNTIME EXTERNAL_DIRS (as Python interpreter sees them)"
echo "================================================================"

read -r -d '' PYTRACE <<'EOF'
import os, sys
sys.path.insert(0, ".")
from hermes_constants import get_hermes_home
from hermes_cli.config import get_config_path
from agent.skill_utils import get_external_skills_dirs, get_all_skills_dirs
from agent.skill_commands import scan_skill_commands
print("HERMES_HOME (runtime):", get_hermes_home())
print("config_path:", get_config_path(), "exists=", get_config_path().exists())
print("external_dirs:", [str(d) for d in get_external_skills_dirs()])
print("all_skills_dirs:", [str(d) for d in get_all_skills_dirs()])
cmds = scan_skill_commands()
print("scanned_commands_total:", len(cmds))
for k in sorted(cmds):
    p = cmds[k].get("skill_md_path","")
    print(f"  {k}  -> {cmds[k]['name']}  ({p})")
EOF

# Try inside container first
if [ -n "${HERMES_PROD_CID:-}" ]; then
  echo "--- 3a. inside container $HERMES_PROD_CID ---"
  docker exec "$HERMES_PROD_CID" bash -c "cd /opt/hermes 2>/dev/null || cd \$(find / -maxdepth 4 -name 'cli.py' -path '*hermes*' 2>/dev/null | head -1 | xargs dirname); python -c \"$PYTRACE\"" 2>&1 | head -40
  echo
  echo "--- 3b. SKILL.md visibility from container ---"
  docker exec "$HERMES_PROD_CID" bash -c 'find / -path /proc -prune -o -name "SKILL.md" -path "*ceo*" -print 2>/dev/null | head -20'
else
  echo "--- 3c. host venv (no container detected) ---"
  if [ -x .venv/bin/python ]; then
    .venv/bin/python -c "$PYTRACE" 2>&1 | head -40
  elif command -v uv >/dev/null 2>&1; then
    uv run --no-sync python -c "$PYTRACE" 2>&1 | head -40
  else
    echo "(no .venv/ and no uv — cannot run runtime trace on host)"
  fi
fi

# --- 4. Process bot config (if any) -----------------------------------------
echo
echo "================================================================"
echo "4. BOT TOKEN PRESENCE (last 6 chars only, never full)"
echo "================================================================"

for f in "$HOST_HERMES_HOME/.env" "$REPO_ROOT/.env"; do
  if [ -f "$f" ]; then
    tok="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$f" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
    if [ -n "$tok" ]; then
      echo "$f: TELEGRAM_BOT_TOKEN=...${tok: -6}"
    else
      echo "$f: no TELEGRAM_BOT_TOKEN entry"
    fi
  fi
done

# --- 5. Verdict --------------------------------------------------------------
echo
echo "================================================================"
echo "5. VERDICT"
echo "================================================================"

if [ -n "${HERMES_PROD_CID:-}" ]; then
  echo "Live container: $HERMES_PROD_CID"
else
  # Stricter filter: exclude IDE/editor and helper processes that may have
  # 'hermes-agent' in their argv as a workspace label.
  HERMES_PROCS="$(
    ps -eo pid,args 2>/dev/null \
      | awk '$0 ~ /(cli\.py|hermes_cli\.main|hermes_cli\.gateway|hermes gateway)/ && $0 !~ /cursor|vscode|electron|grep|production-check|production-fix/' \
      | head -3
  )"
  if [ -n "$HERMES_PROCS" ]; then
    echo "Live host process(es):"
    printf '%s\n' "$HERMES_PROCS" \
      | sed -E 's/(TOKEN|KEY|SECRET|PASSWORD)=[^[:space:]]+/\1=<REDACTED>/g' \
      | cut -c1-200
  else
    echo "NO live Hermes gateway process / container found on THIS host."
    echo "The Telegram bot replying to you is somewhere else."
    echo "Re-run this script on the correct host (VPS / Termux / other Mac)."
  fi
fi
