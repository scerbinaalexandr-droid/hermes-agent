#!/bin/bash
# mac-mirror-setup.sh — read-only LOCAL mirror of the Hermes memory backup repo.
#
# HERMES_TO_96 Etap #12, Risk #9 mitigation: if Railway goes down, your memory/
# and logs/ still exist on the Mac. This pulls the private backup repo
# (scerbinaalexandr-droid/hermes-memory-backup) into a local mirror every 6h and
# marks it read-only so nobody edits the mirror by accident (it is a one-way copy).
#
# Idempotent — clones on first run, fast-forward pulls thereafter. Safe to re-run.
#
# AUTH: uses gh CLI / git credential helper over HTTPS (NOT an SSH key) — matches
#       the 2026-06-01 mac-sync decision (.wiki/decisions.md: mac-sync-via-gh-credentials).
#       No token is stored in this file. Prereq: `gh auth status` shows logged in,
#       and `gh auth setup-git` has wired the git credential helper once.
#
# ─── INSTALL (run by the user — mirror dir is OUTSIDE the project sandbox) ───
#   The mirror lives at ~/Documents/01_CODE/hermes-mirror, which is a separate
#   project folder, so the integrator/user installs it, not the agent.
#
#   1. Copy this script somewhere stable, e.g.:
#        mkdir -p ~/.local/bin
#        cp scripts/ceo-os/mac-mirror-setup.sh ~/.local/bin/
#        chmod +x ~/.local/bin/mac-mirror-setup.sh
#   2. Edit the plist placeholder path, then install the launchd job:
#        cp packaging/launchd/com.alex21.hermes-mirror.plist ~/Library/LaunchAgents/
#        # replace HERMES_MIRROR_SCRIPT_PATH_PLACEHOLDER with the absolute path above
#        launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.alex21.hermes-mirror.plist
#   3. Verify:    launchctl list | grep hermes-mirror
#                 tail -f ~/Library/Logs/hermes-mirror.log
#
#   Uninstall:
#     launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.alex21.hermes-mirror.plist
#     rm ~/Library/LaunchAgents/com.alex21.hermes-mirror.plist
#
# Requires: git, gh (Homebrew). bash + git only at runtime.

set -euo pipefail

# --- CONFIG (override via env if needed) -----------------------------------
BACKUP_REPO_URL="${HERMES_BACKUP_REPO_URL:-https://github.com/scerbinaalexandr-droid/hermes-memory-backup.git}"
MIRROR_DIR="${HERMES_MIRROR_DIR:-$HOME/Documents/01_CODE/hermes-mirror}"
LOG_FILE="${HERMES_MIRROR_LOG:-$HOME/Library/Logs/hermes-mirror.log}"

# --- HELPERS ---------------------------------------------------------------
ts() { date "+%Y-%m-%d %H:%M:%S %Z"; }
log() { echo "[$(ts)] $*" >> "$LOG_FILE"; }

mkdir -p "$(dirname "$LOG_FILE")"

log "=== mirror sync start ==="

# Make the mirror writable for git operations (it may have been locked read-only
# by a previous run). chmod is scoped to the mirror dir only.
unlock() { [ -d "$MIRROR_DIR" ] && chmod -R u+w "$MIRROR_DIR" 2>/dev/null || true; }

# --- 1. CLONE OR PULL ------------------------------------------------------
if [ -d "$MIRROR_DIR/.git" ]; then
  unlock
  cd "$MIRROR_DIR"
  log "pulling repo into $MIRROR_DIR ..."
  if ! git pull --quiet --ff-only 2>>"$LOG_FILE"; then
    log "ERROR: git pull failed. Check 'gh auth status' + 'gh auth setup-git'."
    exit 1
  fi
else
  # Parent must exist; the mirror dir itself is created by git clone.
  mkdir -p "$(dirname "$MIRROR_DIR")"
  log "cloning $BACKUP_REPO_URL -> $MIRROR_DIR"
  if ! git clone --quiet "$BACKUP_REPO_URL" "$MIRROR_DIR" 2>>"$LOG_FILE"; then
    log "ERROR: clone failed. Check BACKUP_REPO_URL + gh CLI auth (run 'gh auth status')."
    log "       Fix git creds once with: gh auth setup-git"
    exit 1
  fi
fi

# --- 2. MARK READ-ONLY -----------------------------------------------------
# Strip the write bit from every tracked file so the mirror is treated as a
# read-only snapshot. .git/ stays writable so the NEXT pull can still fast-forward
# (unlock() above re-grants u+w before each pull regardless).
if find "$MIRROR_DIR" -path "$MIRROR_DIR/.git" -prune -o -type f -print0 2>>"$LOG_FILE" \
     | xargs -0 chmod a-w 2>>"$LOG_FILE"; then
  log "marked mirror files read-only"
else
  log "WARN: could not fully apply read-only flags (non-fatal)"
fi

log "=== mirror sync end (OK) ==="
