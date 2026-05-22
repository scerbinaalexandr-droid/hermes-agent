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

# ---- 2. Seed memory templates (per-file merge) ------------------------------
# For each baked-in template file, copy into the persistent volume only when
# the target is absent OR has zero bytes. Never overwrites populated user
# content. Fixes the case where /opt/data/memory existed from an earlier
# deploy but was missing the 10 default projects / 8 risks templates.
mkdir -p "$HERMES_HOME/memory"
if [ -d "$SEED_MEMORY" ]; then
  seeded_count=0
  for src in "$SEED_MEMORY"/*.md; do
    [ -f "$src" ] || continue
    fname="$(basename "$src")"
    dst="$HERMES_HOME/memory/$fname"
    if [ ! -e "$dst" ] || [ ! -s "$dst" ]; then
      cp "$src" "$dst"
      seeded_count=$((seeded_count + 1))
      echo "[ceo-os-init] Seeded missing/empty: memory/$fname"
    fi
  done
  if [ "$seeded_count" -eq 0 ]; then
    echo "[ceo-os-init] All memory/*.md already populated — nothing to seed"
  else
    echo "[ceo-os-init] Seeded $seeded_count memory file(s) from $SEED_MEMORY"
  fi
else
  echo "[ceo-os-init] WARNING: $SEED_MEMORY missing from image — memory not seeded"
fi

# ---- 2b. Ensure hermes user can write the CEO data --------------------------
# Wrapper runs as root (via tini); upstream entrypoint will drop to hermes
# user (UID 10000 — see Dockerfile). chown all CEO-owned paths so the bot
# can write daily_log.md / decisions.md / per-day logs.
HERMES_UID="${HERMES_UID:-10000}"
HERMES_GID="${HERMES_GID:-10000}"

# Ensure /opt/data/reports exists (used by /report skill output)
mkdir -p "$HERMES_HOME/reports" 2>/dev/null || true

for path in "$HERMES_HOME/memory" \
            "$HERMES_HOME/logs/daily" "$HERMES_HOME/logs/weekly" "$HERMES_HOME/logs/telegram_inputs" \
            "$HERMES_HOME/backups" \
            "$HERMES_HOME/reports" \
            "$HERMES_HOME/cron"; do
  if [ -e "$path" ]; then
    chown -R "$HERMES_UID:$HERMES_GID" "$path" 2>/dev/null || true
  fi
done

# Also chown /opt/data/cron/jobs.json specifically (file may exist outside
# the cron/ dir as a single file in some Hermes setups).
[ -f "$HERMES_HOME/cron/jobs.json" ] && chown "$HERMES_UID:$HERMES_GID" "$HERMES_HOME/cron/jobs.json" 2>/dev/null || true

echo "[ceo-os-init] Ensured $HERMES_UID:$HERMES_GID ownership on CEO data dirs (memory, logs, backups, reports, cron)"

# ---- 3. Point skills/ceo/_lib/memory.py at persistent volume ----------------
export HERMES_CEO_MEMORY_ROOT="$HERMES_HOME/memory"
echo "[ceo-os-init] HERMES_CEO_MEMORY_ROOT=$HERMES_CEO_MEMORY_ROOT"

# ---- 3b. Force re-sync of CEO skills on every boot --------------------------
# Hermes skill-sync copies external_dirs into /opt/data/skills/ for execution.
# If a skill file was updated in the image (new commit), the volume copy may
# remain stale. Wipe + re-link the ceo bundle so each deploy ships fresh code.
# Symlink instead of copy → instant freshness from in-image dir.
if [ -L "$HERMES_HOME/skills/ceo" ] || [ -d "$HERMES_HOME/skills/ceo" ]; then
  rm -rf "$HERMES_HOME/skills/ceo"
fi
mkdir -p "$HERMES_HOME/skills"
ln -s "$CEO_SKILLS_DIR" "$HERMES_HOME/skills/ceo"
chown -h "$HERMES_UID:$HERMES_GID" "$HERMES_HOME/skills/ceo" 2>/dev/null || true
echo "[ceo-os-init] Linked $HERMES_HOME/skills/ceo → $CEO_SKILLS_DIR (fresh per deploy)"

# ---- 3c. Start reports HTTP server in background ----------------------------
# Serves /opt/data/reports/<uuid>.html via Railway public domain.
# Listens on $PORT (Railway default) or $REPORTS_PORT. Daemonized — survives
# parent entrypoint exec. Logs go to /opt/data/logs/reports_server.log.
mkdir -p "$HERMES_HOME/logs" "$HERMES_HOME/reports"
chown "$HERMES_UID:$HERMES_GID" "$HERMES_HOME/logs" "$HERMES_HOME/reports" 2>/dev/null || true

REPORTS_LOG="$HERMES_HOME/logs/reports_server.log"
if [ -f /opt/hermes/docker/reports_server.py ]; then
  # Run as hermes user (gosu drops privs); daemonize via nohup
  nohup gosu "$HERMES_UID:$HERMES_GID" python3 /opt/hermes/docker/reports_server.py \
    >> "$REPORTS_LOG" 2>&1 &
  REPORTS_PID=$!
  echo "[ceo-os-init] Started reports_server (PID $REPORTS_PID), log: $REPORTS_LOG"
else
  echo "[ceo-os-init] WARNING: docker/reports_server.py missing — public URL disabled"
fi

# ---- 4. Hand off to upstream entrypoint -------------------------------------
exec /opt/hermes/docker/entrypoint.sh "$@"
