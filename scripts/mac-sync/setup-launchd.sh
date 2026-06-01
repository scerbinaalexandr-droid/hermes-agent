#!/bin/bash
# setup-launchd.sh — one-time install of hermes-notes-sync launchd job on mac.
#
# What it does:
#   1. Copies hermes-notes-sync.sh to ~/.local/bin/ (created if missing)
#   2. Generates user-specific plist with absolute paths and installs to
#      ~/Library/LaunchAgents/
#   3. Loads the launchd job
#   4. Triggers a first run immediately
#   5. Tails the log so you see what happened
#
# Uninstall:
#   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.alex21.hermes-notes-sync.plist
#   rm ~/Library/LaunchAgents/com.alex21.hermes-notes-sync.plist
#   rm ~/.local/bin/hermes-notes-sync.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_BIN="$HOME/.local/bin/hermes-notes-sync.sh"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST_NAME="com.alex21.hermes-notes-sync.plist"
PLIST_TARGET="$LAUNCH_AGENTS/$PLIST_NAME"
LOG_PATH="$HOME/Library/Logs/hermes-notes-sync.log"

echo "→ Installing hermes-notes-sync on mac (one-time setup)"

# 1. Copy script
mkdir -p "$(dirname "$TARGET_BIN")"
cp "$SCRIPT_DIR/hermes-notes-sync.sh" "$TARGET_BIN"
chmod +x "$TARGET_BIN"
echo "  ✓ script → $TARGET_BIN"

# 2. Generate plist with absolute paths
mkdir -p "$LAUNCH_AGENTS"
sed \
  -e "s|HERMES_SYNC_SCRIPT_PATH_PLACEHOLDER|$TARGET_BIN|g" \
  -e "s|HERMES_LOG_PATH_PLACEHOLDER|$LOG_PATH|g" \
  "$SCRIPT_DIR/com.alex21.hermes-notes-sync.plist" \
  > "$PLIST_TARGET"
echo "  ✓ plist → $PLIST_TARGET"

# 3. Bootstrap into launchd (replaces previous if any)
UID_VAL="$(id -u)"
launchctl bootout "gui/$UID_VAL" "$PLIST_TARGET" 2>/dev/null || true
if launchctl bootstrap "gui/$UID_VAL" "$PLIST_TARGET"; then
  echo "  ✓ launchd job loaded"
else
  echo "  ✗ launchctl bootstrap failed — see system logs"
  exit 1
fi

# 4. Trigger an immediate run
echo "→ Triggering first sync..."
launchctl kickstart -k "gui/$UID_VAL/com.alex21.hermes-notes-sync" || true

# 5. Show log (wait briefly for first write)
sleep 2
echo "→ Log tail (~/Library/Logs/hermes-notes-sync.log):"
echo "---"
tail -n 30 "$LOG_PATH" 2>/dev/null || echo "(no log yet — first run may still be in progress; tail later)"
echo "---"
echo ""
echo "✅ Setup complete. Next run in 6 hours (or 'launchctl kickstart -k gui/$UID_VAL/com.alex21.hermes-notes-sync' to force)."
echo ""
echo "Expected after first successful run:"
echo "  ~/.hermes-mirror/                            ← cloned hermes-memory-backup repo"
echo "  ~/Library/Mobile Documents/com~apple~CloudDocs/ALEX21_VAULT/03 — Notes/   ← rsync target"
echo ""
echo "Prerequisites checklist (if first run errors):"
echo "  • gh CLI authenticated (test: gh auth status — should show 'Logged in')"
echo "  • Git credential helper wired to gh (test: git config --global --get-all credential.helper)"
echo "    Fix if missing: gh auth setup-git"
echo "  • Repo URL in script matches your hermes-memory-backup (default: scerbinaalexandr-droid/hermes-memory-backup)"
echo "  • You have read access to that repo via gh"
