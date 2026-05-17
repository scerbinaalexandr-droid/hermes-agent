#!/usr/bin/env bash
# Production runtime fix for "/brief → Unknown command".
#
# Run on the host where the Hermes Telegram bot answers, AFTER
# production-check.sh confirmed:
#   - HERMES_HOME is at the expected location
#   - skills/ceo/ exists in the repo path baked into config below
#   - the live Hermes process is either a docker container named 'hermes*'
#     or a host venv with a process to be restarted manually
#
# Steps:
#   1. Ensure ~/.hermes/config.yaml contains skills.external_dirs pointing
#      at <REPO>/skills/ceo with an ABSOLUTE path. If config.yaml exists,
#      surgically merge (do not overwrite other keys).
#   2. Restart the Hermes gateway so it picks up the new config + skills.
#   3. Verify post-restart that /brief resolves.
#
# No architecture changes. No new skills. No code refactor.
#
# Usage:
#   bash scripts/ceo-os/production-fix.sh
#   # or to target a non-default repo path:
#   CEO_SKILLS_DIR=/srv/hermes-agent/skills/ceo bash scripts/ceo-os/production-fix.sh

set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
CEO_SKILLS_DIR="${CEO_SKILLS_DIR:-$REPO_ROOT/skills/ceo}"
HOST_HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CONFIG="$HOST_HERMES_HOME/config.yaml"

echo "REPO_ROOT       = $REPO_ROOT"
echo "CEO_SKILLS_DIR  = $CEO_SKILLS_DIR"
echo "HERMES_HOME     = $HOST_HERMES_HOME"
echo "config.yaml     = $CONFIG"

if [ ! -d "$CEO_SKILLS_DIR" ]; then
  echo "ERROR: $CEO_SKILLS_DIR does not exist. Aborting." >&2
  exit 2
fi

mkdir -p "$HOST_HERMES_HOME"

# --- Step 1: surgically add external_dirs to config.yaml --------------------
echo
echo "=== Step 1: ensure skills.external_dirs in $CONFIG ==="

if [ ! -f "$CONFIG" ]; then
  echo "config.yaml absent — creating minimal one."
  cat > "$CONFIG" <<EOF
# Created $(date -u +%FT%TZ) by scripts/ceo-os/production-fix.sh
# Minimal Hermes runtime config — only what is needed for CEO OS Layer
# (V1 Executive OS) skill discovery. Extend with full template from
# cli-config.yaml.example if you want more options.

skills:
  external_dirs:
    - $CEO_SKILLS_DIR
EOF
  echo "Wrote $CONFIG."
else
  echo "config.yaml exists — checking for skills.external_dirs entry."
  if grep -qF "    - $CEO_SKILLS_DIR" "$CONFIG"; then
    echo "Already present — no change."
  else
    if grep -qE "^skills:" "$CONFIG"; then
      if grep -qE "^[[:space:]]*external_dirs:" "$CONFIG"; then
        TMP="$(mktemp)"
        awk -v p="$CEO_SKILLS_DIR" '
          /^[[:space:]]*external_dirs:/ {
            print
            print "    - " p
            inserted = 1
            next
          }
          { print }
          END { if (!inserted) exit 1 }
        ' "$CONFIG" > "$TMP" && mv "$TMP" "$CONFIG"
        echo "Appended $CEO_SKILLS_DIR under existing skills.external_dirs."
      else
        printf "\n  external_dirs:\n    - %s\n" "$CEO_SKILLS_DIR" >> "$CONFIG"
        echo "Added external_dirs subkey under existing skills: block."
      fi
    else
      printf "\nskills:\n  external_dirs:\n    - %s\n" "$CEO_SKILLS_DIR" >> "$CONFIG"
      echo "Appended skills: block at end of config.yaml."
    fi
  fi
fi

echo
echo "--- config.yaml now ---"
cat "$CONFIG"

# --- Step 2: restart gateway -------------------------------------------------
echo
echo "=== Step 2: restart Hermes gateway ==="

CID=""
if command -v docker >/dev/null 2>&1; then
  CID="$(docker ps -q --filter 'name=hermes' 2>/dev/null | head -1)"
fi

if [ -n "$CID" ]; then
  echo "Found docker container: $CID — restarting."
  docker restart "$CID" >/dev/null && echo "Restarted." || { echo "docker restart FAILED" >&2; exit 3; }
  echo "Waiting 8s for gateway to reattach to Telegram..."
  sleep 8
elif command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet hermes 2>/dev/null; then
  echo "systemd unit 'hermes' is active — restarting."
  systemctl restart hermes && echo "Restarted." || exit 3
  sleep 5
elif command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet hermes-gateway 2>/dev/null; then
  echo "user systemd unit 'hermes-gateway' active — restarting."
  systemctl --user restart hermes-gateway && echo "Restarted." || exit 3
  sleep 5
else
  echo "No managed service detected. Manual action required:"
  echo "  - If you launch with 'hermes gateway' in tmux/screen — kill and restart."
  echo "  - If launched via 'docker compose up -d hermes' — run 'docker compose restart hermes'."
  echo "  - After manual restart re-run this script (idempotent)."
fi

# --- Step 3: post-restart verification --------------------------------------
echo
echo "=== Step 3: post-restart verification ==="

read -r -d '' PYCHECK <<'EOF'
import sys
sys.path.insert(0, ".")
from agent.skill_commands import scan_skill_commands, resolve_skill_command_key, build_skill_invocation_message
cmds = scan_skill_commands()
ceo_keys = sorted(k for k in cmds if cmds[k]["name"] in {"brief","evening","week","projects","risks","capture","backup"})
print(f"CEO skill commands visible: {len(ceo_keys)}/7")
for k in ceo_keys:
    print(f"  {k}  -> {cmds[k]['name']}")
print(f"resolve_skill_command_key('brief') = {resolve_skill_command_key('brief')}")
msg = build_skill_invocation_message('/brief')
print(f"build_skill_invocation_message('/brief') = {len(msg) if msg else 0} chars")
EOF

if [ -n "$CID" ]; then
  docker exec "$CID" bash -c "cd /opt/hermes 2>/dev/null || cd \$(dirname \$(find / -maxdepth 4 -name cli.py -path '*hermes*' 2>/dev/null | head -1)); python -c \"$PYCHECK\"" 2>&1 | head -20
else
  if [ -x .venv/bin/python ]; then
    .venv/bin/python -c "$PYCHECK" 2>&1 | head -20
  elif command -v uv >/dev/null 2>&1; then
    uv run --no-sync python -c "$PYCHECK" 2>&1 | head -20
  else
    echo "(no host python to verify — open Telegram and try /brief)"
  fi
fi

echo
echo "=== DONE ==="
echo "Now in Telegram: send /brief to the bot."
echo "If still 'Unknown command' — gateway has not reattached yet; wait 30s and retry,"
echo "or check 'docker logs <hermes-container> --tail 80' for connection errors."
