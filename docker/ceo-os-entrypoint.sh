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

# ---- 1. Ensure config.yaml (skills + model + hooks + guardrails) ------------
# Delegated to a self-healing Python helper that ALWAYS writes valid YAML.
# Replaces the previous bash/awk merge, which corrupted config.yaml whenever a
# prior `/model --global` had rewritten it via yaml.dump (2-space list indent):
# the awk branch mixed a 4-space list item with the 2-space one -> invalid YAML
# -> model.default wiped on the next boot ("No models provided" incident,
# 2026-05-24). The helper rebuilds a clean config if the file is unparseable
# and restores model.default from $HERMES_MODEL.
# Run with the app venv python (has pyyaml); fall back to python3.
HERMES_PY="/opt/hermes/.venv/bin/python"
[ -x "$HERMES_PY" ] || HERMES_PY="python3"
if "$HERMES_PY" /opt/hermes/scripts/hooks/ensure_config.py; then
  echo "[ceo-os-init] config.yaml ensured via ensure_config.py ($HERMES_PY)"
else
  echo "[ceo-os-init] WARNING: ensure_config.py exited non-zero — config left as-is"
fi

# Ensure the hooks audit-log dir exists (chowned in section 2b below).
mkdir -p "$HERMES_HOME/logs/hooks"

# ---- 1c. Stage backup script into the cron-allowed dir (INSTRUCTION_03) -----
# Hermes cron `--script` must resolve under $HERMES_HOME/scripts/. Copy the
# in-image backup.py there on every boot (fresh per deploy). The cron JOB is
# created once via `hermes cron create ... --no-agent` (see backup/SKILL.md) —
# NOT auto-created here, to keep boot simple and avoid CLI-at-boot fragility.
# Best-effort from here through memory seeding: staging scripts and seeding
# templates must NEVER abort the boot (e.g. a disk-full `cp` under `set -e`
# would crash the container and take the bot fully offline). Re-enabled after.
set +e
mkdir -p "$HERMES_HOME/scripts"
if [ -f /opt/hermes/skills/ceo/backup/scripts/backup.py ]; then
  cp /opt/hermes/skills/ceo/backup/scripts/backup.py "$HERMES_HOME/scripts/backup.py"
  chown "${HERMES_UID:-10000}:${HERMES_GID:-10000}" "$HERMES_HOME/scripts/backup.py" 2>/dev/null || true
  echo "[ceo-os-init] Staged backup.py → $HERMES_HOME/scripts/backup.py"
fi
if [ -f /opt/hermes/skills/ceo/cost/scripts/cost_monitor.py ]; then
  cp /opt/hermes/skills/ceo/cost/scripts/cost_monitor.py "$HERMES_HOME/scripts/cost_monitor.py"
  chown "${HERMES_UID:-10000}:${HERMES_GID:-10000}" "$HERMES_HOME/scripts/cost_monitor.py" 2>/dev/null || true
  echo "[ceo-os-init] Staged cost_monitor.py → $HERMES_HOME/scripts/cost_monitor.py"
fi
if [ -f /opt/hermes/skills/ceo/telemetry/scripts/telemetry_report.py ]; then
  cp /opt/hermes/skills/ceo/telemetry/scripts/telemetry_report.py "$HERMES_HOME/scripts/telemetry_report.py"
  chown "${HERMES_UID:-10000}:${HERMES_GID:-10000}" "$HERMES_HOME/scripts/telemetry_report.py" 2>/dev/null || true
  echo "[ceo-os-init] Staged telemetry_report.py → $HERMES_HOME/scripts/telemetry_report.py"
fi
if [ -f /opt/hermes/skills/ceo/inbox/scripts/inbox_triage.py ]; then
  cp /opt/hermes/skills/ceo/inbox/scripts/inbox_triage.py "$HERMES_HOME/scripts/inbox_triage.py"
  chown "${HERMES_UID:-10000}:${HERMES_GID:-10000}" "$HERMES_HOME/scripts/inbox_triage.py" 2>/dev/null || true
  echo "[ceo-os-init] Staged inbox_triage.py → $HERMES_HOME/scripts/inbox_triage.py"
fi
if [ -f /opt/hermes/skills/ceo/birthday/scripts/birthday.py ]; then
  cp /opt/hermes/skills/ceo/birthday/scripts/birthday.py "$HERMES_HOME/scripts/birthday.py"
  chown "${HERMES_UID:-10000}:${HERMES_GID:-10000}" "$HERMES_HOME/scripts/birthday.py" 2>/dev/null || true
  echo "[ceo-os-init] Staged birthday.py → $HERMES_HOME/scripts/birthday.py"
fi
if [ -f /opt/hermes/skills/ceo/notes/scripts/notes_log.py ]; then
  cp /opt/hermes/skills/ceo/notes/scripts/notes_log.py "$HERMES_HOME/scripts/notes_log.py"
  chown "${HERMES_UID:-10000}:${HERMES_GID:-10000}" "$HERMES_HOME/scripts/notes_log.py" 2>/dev/null || true
  echo "[ceo-os-init] Staged notes_log.py → $HERMES_HOME/scripts/notes_log.py"
fi
if [ -f /opt/hermes/skills/ceo/health/scripts/api_health.py ]; then
  cp /opt/hermes/skills/ceo/health/scripts/api_health.py "$HERMES_HOME/scripts/api_health.py"
  chown "${HERMES_UID:-10000}:${HERMES_GID:-10000}" "$HERMES_HOME/scripts/api_health.py" 2>/dev/null || true
  echo "[ceo-os-init] Staged api_health.py → $HERMES_HOME/scripts/api_health.py"
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
set -e  # end best-effort staging/seeding — ownership below stays strict

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
            "$HERMES_HOME/logs/hooks" \
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

# Self-heal ALL ownership across the volume. The per-dir chowns above miss
# top-level files like google_token.json / google_client_secret.json — when
# one ends up root-owned (e.g. created in an `ssh`-as-root session), the hermes
# app silently loses Google access or goes cron-blind until someone notices.
# Sweep every path NOT already owned by hermes and chown it back. Cheap:
# `! -user` skips the (vast) majority already correct; lost+found stays root
# for fsck. Makes ownership drift self-correcting on every boot — the root
# cause of the 2026-06-30 google_token.json + cron/jobs.json outages.
find "$HERMES_HOME" -mindepth 1 \
     -path "$HERMES_HOME/lost+found" -prune -o \
     \( ! -user "$HERMES_UID" -exec chown -h "$HERMES_UID:$HERMES_GID" {} + \) \
     2>/dev/null || true

echo "[ceo-os-init] Ensured $HERMES_UID:$HERMES_GID ownership across $HERMES_HOME (CEO dirs + self-heal of any root-owned files)"

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

# ---- 3d. Start Tailscale + hermes-webui (iPhone app backend) ----------------
# Both power the Hermex iOS app. Previously they were started by hand over ssh,
# with binaries in /tmp — so every redeploy silently killed them and the app
# went dead. Now they live on the volume and start here, like everything else.
# Failures are non-fatal: Telegram must keep working even if the app backend is
# down.
TS_DIR="$HERMES_HOME/tailscale"
TS_SOCK="$TS_DIR/state/tailscaled.sock"
TS_LOG="$HERMES_HOME/logs/tailscaled.log"
if [ -x "$TS_DIR/bin/tailscaled" ]; then
  chown -R "$HERMES_UID:$HERMES_GID" "$TS_DIR" 2>/dev/null || true
  nohup gosu "$HERMES_UID:$HERMES_GID" "$TS_DIR/bin/tailscaled" \
    --tun=userspace-networking \
    --state="$TS_DIR/state/tailscaled.state" \
    --socket="$TS_SOCK" >> "$TS_LOG" 2>&1 &
  echo "[ceo-os-init] Started tailscaled (PID $!), log: $TS_LOG"
  # Give the daemon a moment to create its socket before bringing the node up.
  sleep 3
  # The node is already authorised (state file on the volume), so `up` only
  # re-attaches it — no auth key needed.
  gosu "$HERMES_UID:$HERMES_GID" "$TS_DIR/bin/tailscale" --socket="$TS_SOCK" \
    up --hostname=hermes-webui --accept-dns=false >> "$TS_LOG" 2>&1 \
    && echo "[ceo-os-init] Tailscale node up" \
    || echo "[ceo-os-init] WARNING: tailscale up failed — see $TS_LOG"
else
  echo "[ceo-os-init] Tailscale not installed at $TS_DIR — skipping"
fi

WEBUI_DIR="$HERMES_HOME/home/hermes-webui"
WEBUI_LOG="$HERMES_HOME/logs/hermes-webui.log"
WEBUI_PORT="${HERMES_WEBUI_PORT:-8787}"
# Password source order: service env, else a 0600 file on the volume. The file
# lets the app backend be configured without touching the Railway dashboard.
WEBUI_PW_FILE="$HERMES_HOME/webui-password"
if [ -z "$HERMES_WEBUI_PASSWORD" ] && [ -f "$WEBUI_PW_FILE" ]; then
  HERMES_WEBUI_PASSWORD="$(cat "$WEBUI_PW_FILE")"
  export HERMES_WEBUI_PASSWORD
  chown "$HERMES_UID:$HERMES_GID" "$WEBUI_PW_FILE" 2>/dev/null || true
  chmod 600 "$WEBUI_PW_FILE" 2>/dev/null || true
fi
# Interpreter: prefer the Hermes venv — it has yaml and the agent packages the
# web UI imports. The volume's own venv is unreliable: the bootstrap installer
# overwrote it with a bare symlink to system python, which lacks yaml and made
# server.py die on import.
if [ -x /opt/hermes/.venv/bin/python ]; then
  WEBUI_PY=/opt/hermes/.venv/bin/python
else
  WEBUI_PY=python3
fi
if [ -f "$WEBUI_DIR/server.py" ]; then
  if [ -z "$HERMES_WEBUI_PASSWORD" ]; then
    echo "[ceo-os-init] WARNING: HERMES_WEBUI_PASSWORD unset — web UI would be open to anyone on the tailnet; not starting it"
  else
    # Exported explicitly so the child inherits them regardless of how the
    # service env is delivered. The LLM keys come from the service env — their
    # absence is exactly what broke the app before.
    # Launch server.py directly, NOT bootstrap.py: bootstrap is an installer that
    # re-provisions Hermes on every run (downloads Node, expects a git checkout)
    # and aborts with "Directory exists but is not a git repository" — which is
    # exactly why the app showed "Офлайн" after a redeploy. The runtime is
    # already provisioned on the volume; we only need the server.
    nohup gosu "$HERMES_UID:$HERMES_GID" env \
      HERMES_HOME="$HERMES_HOME" \
      HERMES_WEBUI_HOST="${HERMES_WEBUI_HOST:-0.0.0.0}" \
      HERMES_WEBUI_PORT="$WEBUI_PORT" \
      HERMES_WEBUI_STATE_DIR="${HERMES_WEBUI_STATE_DIR:-$HERMES_HOME/webui}" \
      HERMES_WEBUI_AGENT_DIR="${HERMES_WEBUI_AGENT_DIR:-/opt/hermes}" \
      HERMES_WEBUI_TRUST_FORWARDED_PROTO=1 \
      HERMES_WEBUI_SECURE=1 \
      HERMES_WEBUI_ALLOWED_ORIGINS="${HERMES_WEBUI_ALLOWED_ORIGINS:-https://${HERMES_PUBLIC_HOST:-hermes-production-99b8.up.railway.app}}" \
      sh -c "cd '$WEBUI_DIR' && exec $WEBUI_PY server.py" \
      >> "$WEBUI_LOG" 2>&1 &
    echo "[ceo-os-init] Started hermes-webui on :$WEBUI_PORT (PID $!), log: $WEBUI_LOG"
  fi
else
  echo "[ceo-os-init] hermes-webui not installed at $WEBUI_DIR — skipping"
fi

# ---- 3e. Drop a rejected Telegram token before the gateway sees it ----------
# The gateway aborts startup when every *configured* platform fails to connect
# (gateway/run.py: enabled_platform_count > 0 and connected_count == 0 → return
# False), but keeps running for cron when none is configured at all. So a token
# revoked in BotFather took down the whole service — cron, reports and the
# iPhone app included — not just Telegram. Probe it here and unset on a hard
# rejection, so the assistant degrades to "no Telegram" instead of dying.
# Only 401/404 count: network hiccups must not disable a working bot.
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
  TG_CODE=$(curl -s -o /dev/null -m 15 -w '%{http_code}' \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" 2>/dev/null || echo "000")
  case "$TG_CODE" in
    401|404)
      echo "[ceo-os-init] WARNING: Telegram rejected the bot token (HTTP $TG_CODE) — starting without Telegram so cron and the web UI stay up. Issue a new token in @BotFather and set TELEGRAM_BOT_TOKEN."
      unset TELEGRAM_BOT_TOKEN
      ;;
    200)
      echo "[ceo-os-init] Telegram token OK"
      ;;
    *)
      echo "[ceo-os-init] Telegram token probe inconclusive (HTTP $TG_CODE) — leaving it to the gateway"
      ;;
  esac
fi

# ---- 4. Hand off to upstream entrypoint -------------------------------------
exec /opt/hermes/docker/entrypoint.sh "$@"
