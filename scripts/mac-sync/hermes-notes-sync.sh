#!/bin/bash
# hermes-notes-sync.sh — pulls Hermes notes from private GitHub backup repo
# and rsyncs into Obsidian ALEX21_VAULT/03 — Notes/.
#
# Runs via launchd plist com.alex21.hermes-notes-sync every 6 hours.
# Idempotent — safe to run any time. Logs to ~/Library/Logs/hermes-notes-sync.log.
#
# Setup:
#   1. Edit BACKUP_REPO_URL below if your hermes-memory-backup repo URL differs.
#   2. Install via setup-launchd.sh
#
# Requires: git, rsync (both built into macOS).

set -euo pipefail

# --- CONFIG (edit if needed) -----------------------------------------------
BACKUP_REPO_URL="${HERMES_BACKUP_REPO_URL:-https://github.com/scerbinaalexandr-droid/hermes-memory-backup.git}"
LOCAL_MIRROR="${HERMES_LOCAL_MIRROR:-$HOME/.hermes-mirror}"
OBSIDIAN_NOTES_DIR="${HERMES_OBSIDIAN_NOTES:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/ALEX21_VAULT/03 — Notes}"
LOG_FILE="${HERMES_SYNC_LOG:-$HOME/Library/Logs/hermes-notes-sync.log}"

# --- HELPERS ---------------------------------------------------------------
ts() { date "+%Y-%m-%d %H:%M:%S %Z"; }
log() { echo "[$(ts)] $*" >> "$LOG_FILE"; }

mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$LOCAL_MIRROR"
mkdir -p "$OBSIDIAN_NOTES_DIR"

log "=== sync start ==="

# --- 1. CLONE OR PULL ------------------------------------------------------
if [ -d "$LOCAL_MIRROR/.git" ]; then
  cd "$LOCAL_MIRROR"
  log "pulling repo..."
  if ! git pull --quiet --ff-only 2>>"$LOG_FILE"; then
    log "ERROR: git pull failed"
    exit 1
  fi
else
  log "cloning $BACKUP_REPO_URL → $LOCAL_MIRROR"
  if ! git clone --quiet "$BACKUP_REPO_URL" "$LOCAL_MIRROR" 2>>"$LOG_FILE"; then
    log "ERROR: clone failed. Check BACKUP_REPO_URL + gh CLI auth (run 'gh auth status')."
    exit 1
  fi
fi

# --- 2. RSYNC NOTES INTO VAULT --------------------------------------------
if [ ! -d "$LOCAL_MIRROR/logs/notes" ]; then
  log "no logs/notes/ in mirror yet (no notes saved on prod). Skipping rsync."
  log "=== sync end (no-op) ==="
  exit 0
fi

# Use --update to never overwrite newer local edits; --no-perms because iCloud
# strips permissions anyway; --delete is OFF — Obsidian additions stay safe.
if rsync -av --update --no-perms \
    "$LOCAL_MIRROR/logs/notes/" \
    "$OBSIDIAN_NOTES_DIR/" \
    >>"$LOG_FILE" 2>&1; then
  log "rsync OK → $OBSIDIAN_NOTES_DIR"
else
  log "ERROR: rsync failed"
  exit 1
fi

log "=== sync end ==="
