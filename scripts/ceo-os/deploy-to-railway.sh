#!/usr/bin/env bash
# Deploy CEO OS Layer (V1) to existing Hermes Railway deployment.
#
# Production target:
#   Railway project 4e83ef6c-268f-4021-81f0-6807906432a7
#   Service         ab136f58-0bfb-49fb-9c12-8fe38210e301
#   Bot             @Hermes_Alex21_bot
#
# What this does (steps printed before each action; aborts on first error):
#   1. Verify prerequisites (railway CLI, git, repo state).
#   2. Show preview of what will deploy.
#   3. Confirm with user.
#   4. Commit pending work to local main (optional, only if user opts in).
#   5. `railway link` to the Hermes project/service.
#   6. `railway up --detach` — uploads context, builds image, deploys.
#      Image has new .dockerignore (allowing skills/ceo SKILL.md),
#      new Dockerfile ENTRYPOINT pointing at docker/ceo-os-entrypoint.sh,
#      and the ceo-os-entrypoint.sh that seeds /opt/data/config.yaml on
#      first start.
#   7. Tail build logs.
#   8. After deploy completes, print verification checklist.
#
# DOES NOT touch:
#   - Telegram bot token / Anthropic API key (Railway secrets, unchanged).
#   - Upstream Hermes core (docker/entrypoint.sh, agent/, cli.py — untouched).
#   - Existing /opt/data/memory content if any (ceo-os-entrypoint.sh seeds
#     only on first boot; subsequent boots leave /opt/data/memory alone).
#
# Usage:
#   bash scripts/ceo-os/deploy-to-railway.sh             # interactive
#   YES=1 bash scripts/ceo-os/deploy-to-railway.sh       # non-interactive
#
# Environment overrides:
#   RAILWAY_PROJECT_ID, RAILWAY_SERVICE_ID — to retarget elsewhere.

set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PROJECT_ID="${RAILWAY_PROJECT_ID:-4e83ef6c-268f-4021-81f0-6807906432a7}"
SERVICE_ID="${RAILWAY_SERVICE_ID:-ab136f58-0bfb-49fb-9c12-8fe38210e301}"

ok()    { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[33m⚠\033[0m %s\n' "$*"; }
fail()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }
step()  { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

# --- 1. Prerequisites -------------------------------------------------------
step "1. Prerequisites"

command -v railway >/dev/null 2>&1 || fail "railway CLI not found. brew install railway"
railway whoami >/dev/null 2>&1 || fail "railway not logged in. Run: railway login"
ok "railway CLI: $(railway --version 2>&1 | head -1)"
ok "logged in as: $(railway whoami 2>&1 | tail -1)"

command -v git >/dev/null 2>&1 || fail "git not found"
git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1 || fail "$REPO_ROOT is not a git repo"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
ok "git branch: $BRANCH"

# Sanity: required files exist
for f in Dockerfile docker/ceo-os-entrypoint.sh docker/entrypoint.sh skills/ceo/brief/SKILL.md .dockerignore; do
  [ -f "$f" ] || fail "missing required file: $f"
done
[ -x docker/ceo-os-entrypoint.sh ] || fail "docker/ceo-os-entrypoint.sh not executable. Run: chmod +x $_"
ok "required files present"

# Sanity: ENTRYPOINT in Dockerfile points at our wrapper
grep -q 'ceo-os-entrypoint.sh' Dockerfile || fail "Dockerfile ENTRYPOINT does not point at ceo-os-entrypoint.sh"
ok "Dockerfile ENTRYPOINT wired to wrapper"

# Sanity: .dockerignore whitelists CEO skill files
grep -q '!skills/ceo/\*\*/SKILL.md' .dockerignore || fail ".dockerignore missing whitelist for skills/ceo/**/SKILL.md"
ok ".dockerignore whitelists CEO skill files"

# --- 2. Preview --------------------------------------------------------------
step "2. Preview of deploy"

echo "Repo root:         $REPO_ROOT"
echo "Railway project:   $PROJECT_ID"
echo "Railway service:   $SERVICE_ID"
echo
echo "Files staged in build context (post-.dockerignore filtering, top 20):"
# Approximate: list everything not matching obvious dockerignore patterns.
git ls-files --others --cached --exclude-standard 2>/dev/null \
  | grep -vE '^(\.wiki/|backups/|logs/|node_modules/|\.venv/)' \
  | grep -E '^(skills/ceo/|memory/|SOP/|CLAUDE\.md|docker/ceo-os-entrypoint\.sh|Dockerfile|\.dockerignore)' \
  | sort | head -30

echo
echo "Local git status (uncommitted):"
git status --short

echo
echo "Build will:"
echo "  - bake skills/ceo/, memory/ templates, SOP/, CLAUDE.md, docker/ceo-os-entrypoint.sh into image at /opt/hermes/"
echo "  - on container start, seed /opt/data/config.yaml + /opt/data/memory (only if empty)"
echo "  - export HERMES_CEO_MEMORY_ROOT=/opt/data/memory so /capture, /evening, /week write to persistent volume"
echo "  - then exec upstream gateway run (Telegram polling reconnects)"

if [ "${YES:-0}" != "1" ]; then
  printf '\nProceed with deploy? [y/N] '
  read -r reply
  case "$reply" in
    y|Y|yes|YES) ;;
    *) fail "Aborted by user." ;;
  esac
fi

# --- 3. Optional: commit pending CEO OS work to local main ------------------
step "3. Local git commit (optional)"

if [ -n "$(git status --short 2>/dev/null)" ]; then
  warn "Uncommitted changes detected. Railway uploads working directory (not just committed)."
  warn "Skipping auto-commit; railway up will ship current files anyway."
  warn "After successful deploy, recommend manually: git add ... && git commit -m 'feat(ceo-os): V1 production deploy'"
else
  ok "Working tree clean."
fi

# --- 4. Railway link --------------------------------------------------------
step "4. Railway link"

# `railway link` is idempotent — re-links if already linked
railway link --project "$PROJECT_ID" --service "$SERVICE_ID" 2>&1 | head -10 || fail "railway link failed"
ok "linked to project $PROJECT_ID, service $SERVICE_ID"

# --- 5. Railway up ----------------------------------------------------------
step "5. railway up (build + deploy)"

echo "This may take 3-6 minutes (image build + push + deploy)..."
echo "Use Ctrl-C to abort upload (does NOT cancel an already-started build)."
echo

railway up --detach 2>&1 | tee /tmp/railway-up.log

# --- 6. Wait + verify -------------------------------------------------------
step "6. Post-deploy verification"

cat <<'POST'

Wait ~3 minutes, then verify:

  1. Open Railway dashboard:
     https://railway.app/project/4e83ef6c-268f-4021-81f0-6807906432a7

     - Latest deployment should show "Active" within ~5 min
     - Logs should include lines like:
         [ceo-os-init] Created /opt/data/config.yaml with external_dirs=/opt/hermes/skills/ceo
         [ceo-os-init] Seeded /opt/data/memory from /opt/hermes/memory (first boot only)
         [ceo-os-init] HERMES_CEO_MEMORY_ROOT=/opt/data/memory
     - After init logs: normal Hermes gateway startup (Telegram polling)

  2. In Telegram, message @Hermes_Alex21_bot:
       /commands
     Expected: list including /brief, /evening, /week, /projects, /risks, /capture, /backup

  3. Test end-to-end:
       /brief
     Expected: structured Daily Briefing per blueprint §07 (Date, Main Focus,
     Top 3 Business, Top 3 Personal, Meetings, Deadlines, Health Action,
     Family Touchpoint, Energy Warning, Main Risk Today, One Important Question)

  4. If /brief shows "Unknown command" 30+ seconds after deploy completes:
       - Railway dashboard → service → ⋯ → Redeploy (forces fresh start)
       - Re-check logs for [ceo-os-init] lines
       - If [ceo-os-init] absent → entrypoint not running our wrapper; check Dockerfile

POST

ok "deploy-to-railway.sh finished."
