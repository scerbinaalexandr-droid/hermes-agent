#!/usr/bin/env bash
# CEO OS Layer (V1 Executive OS) — first-boot init wrapper.
#
# Sits in front of upstream /opt/hermes/docker/entrypoint.sh. Does ONE thing:
#   - On every container start, ensure HERMES_HOME/config.yaml contains
#     skills.external_dirs pointing at /opt/hermes/skills/ceo (so the
#     Hermes skill loader auto-discovers /brief, /evening, /week,
#     /projects, /risks, /capture, /backup).
#   - On FIRST start only (when HERMES_HOME/memory is absent), seed it
#     with template files baked into the image. NEVER overwrites
#     existing user content (memory edits made via /capture, /evening,
#     /week skills are persistent across deploys).
#   - Export HERMES_CEO_MEMORY_ROOT so skills/ceo/_lib/memory.py reads from
#     the persistent /opt/data/memory directory, not the in-image fallback.
#
# Then hands off (exec) to upstream entrypoint with the original CMD args.
#
# Idempotent: safe to run on every restart.

set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"
CEO_SKILLS_DIR="/opt/hermes/skills/ceo"
CONFIG="$HERMES_HOME/config.yaml"
SEED_MEMORY="/opt/hermes/memory"

mkdir -p "$HERMES_HOME"

# ---- 1. Ensure skills.external_dirs in config.yaml --------------------------
if [ ! -f "$CONFIG" ]; then
  cat > "$CONFIG" <<EOF
# Created $(date -u +%FT%TZ) by ceo-os-entrypoint.sh
# Minimal Hermes runtime config — enables CEO OS Layer skill discovery.
# Extend with full template from cli-config.yaml.example if you want more options.
skills:
  external_dirs:
    - $CEO_SKILLS_DIR
EOF
  echo "[ceo-os-init] Created $CONFIG with external_dirs=$CEO_SKILLS_DIR"
elif ! grep -qF "    - $CEO_SKILLS_DIR" "$CONFIG"; then
  if grep -qE "^skills:" "$CONFIG"; then
    if grep -qE "^[[:space:]]*external_dirs:" "$CONFIG"; then
      # Normalize inline empty list (`external_dirs: []`) to block-start
      # (`external_dirs:`) BEFORE appending — otherwise mixing produces
      # invalid YAML (block sequence under flow mapping).
      TMP="$(mktemp)"
      awk -v p="$CEO_SKILLS_DIR" '
        /^[[:space:]]*external_dirs:[[:space:]]*\[\][[:space:]]*$/ {
          sub(/:[[:space:]]*\[\][[:space:]]*$/, ":")
          print
          print "    - " p
          inserted = 1
          next
        }
        /^[[:space:]]*external_dirs:[[:space:]]*$/ {
          print
          print "    - " p
          inserted = 1
          next
        }
        { print }
      ' "$CONFIG" > "$TMP" && mv "$TMP" "$CONFIG"
      echo "[ceo-os-init] Appended $CEO_SKILLS_DIR under existing skills.external_dirs"
    else
      printf "\n  external_dirs:\n    - %s\n" "$CEO_SKILLS_DIR" >> "$CONFIG"
      echo "[ceo-os-init] Added external_dirs subkey under existing skills: block"
    fi
  else
    printf "\nskills:\n  external_dirs:\n    - %s\n" "$CEO_SKILLS_DIR" >> "$CONFIG"
    echo "[ceo-os-init] Appended skills block to existing $CONFIG"
  fi
else
  echo "[ceo-os-init] $CONFIG already has $CEO_SKILLS_DIR — no change"
fi

# ---- 2. Seed memory templates on first boot ---------------------------------
# Only if memory dir is absent OR empty. Never overwrites existing files.
if [ ! -d "$HERMES_HOME/memory" ] || [ -z "$(ls -A "$HERMES_HOME/memory" 2>/dev/null)" ]; then
  if [ -d "$SEED_MEMORY" ]; then
    mkdir -p "$HERMES_HOME/memory"
    cp -rn "$SEED_MEMORY"/. "$HERMES_HOME/memory"/
    echo "[ceo-os-init] Seeded $HERMES_HOME/memory from $SEED_MEMORY (first boot only)"
  else
    echo "[ceo-os-init] WARNING: $SEED_MEMORY missing from image — memory not seeded"
  fi
else
  echo "[ceo-os-init] $HERMES_HOME/memory already populated — skipping seed"
fi

# ---- 2b. Ensure hermes user can write the CEO data --------------------------
# Wrapper runs as root (via tini); upstream entrypoint will drop to hermes
# user (UID 10000 — see Dockerfile). chown all CEO-owned paths so the bot
# can write daily_log.md / decisions.md / per-day logs.
HERMES_UID="${HERMES_UID:-10000}"
HERMES_GID="${HERMES_GID:-10000}"
for path in "$HERMES_HOME/memory" "$HERMES_HOME/logs/daily" "$HERMES_HOME/logs/weekly" "$HERMES_HOME/logs/telegram_inputs" "$HERMES_HOME/backups"; do
  if [ -e "$path" ]; then
    chown -R "$HERMES_UID:$HERMES_GID" "$path" 2>/dev/null || true
  fi
done
echo "[ceo-os-init] Ensured $HERMES_UID:$HERMES_GID ownership on CEO data dirs"

# ---- 3. Point skills/ceo/_lib/memory.py at persistent volume ----------------
export HERMES_CEO_MEMORY_ROOT="$HERMES_HOME/memory"
echo "[ceo-os-init] HERMES_CEO_MEMORY_ROOT=$HERMES_CEO_MEMORY_ROOT"

# ---- 4. Hand off to upstream entrypoint -------------------------------------
exec /opt/hermes/docker/entrypoint.sh "$@"
