#!/usr/bin/env bash
# Pull latest code + rebuild + publish CUSTOMER dashboard only (dashboard.voxbulk.com).
#
# GitHub push does NOT update the live site — run this ON THE VPS.
#
# Usage:
#   cd /www/voxbulk
#   bash scripts/vps-sync-dashboard.sh
#
# Feature branch (your Create Survey work is here until merged to main):
#   VOX_GIT_BRANCH=feat/wa-survey-template-library bash scripts/vps-sync-dashboard.sh
#
# Skip git pull (rebuild current tree only):
#   VOX_SKIP_GIT=1 bash scripts/vps-sync-dashboard.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"
VOX_DASH_DIST="${VOX_DASH_DIST:-/www/wwwroot/dashboard.voxbulk.com}"
GIT_REMOTE="${VOX_GIT_REMOTE:-origin}"
GIT_BRANCH="${VOX_GIT_BRANCH:-main}"

echo "=== VoxBulk dashboard sync ==="
echo "Repo:    $ROOT"
echo "Branch:  $GIT_REMOTE/$GIT_BRANCH"
echo "Wwwroot: $VOX_DASH_DIST"
echo ""

if [[ "${VOX_SKIP_GIT:-0}" != "1" ]]; then
  cd "$ROOT"
  if ! git diff --quiet deploy-vps.sh vox.sh scripts/vps-sync-dashboard.sh scripts/vps-update-ui.sh 2>/dev/null; then
    echo ">>> Resetting local edits to deploy scripts so pull can proceed"
    git checkout -- deploy-vps.sh vox.sh scripts/vps-sync-dashboard.sh scripts/vps-update-ui.sh 2>/dev/null || true
  fi
  echo ">>> git fetch + pull"
  git fetch "$GIT_REMOTE" "$GIT_BRANCH"
  git checkout "$GIT_BRANCH" 2>/dev/null || git checkout -b "$GIT_BRANCH" "$GIT_REMOTE/$GIT_BRANCH"
  git pull --ff-only "$GIT_REMOTE" "$GIT_BRANCH"
  echo ">>> At commit: $(git rev-parse --short HEAD) — $(git log -1 --format='%s')"
else
  echo ">>> VOX_SKIP_GIT=1 — using current files"
  echo ">>> At commit: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
fi

if [[ -f "$ROOT/scripts/sync-brand-assets.mjs" ]]; then
  node "$ROOT/scripts/sync-brand-assets.mjs"
fi

echo ">>> npm install + build (dashboard)"
cd "$DASH_DIR"
npm install
npm run build

[[ -f dist/client/index.html ]] || { echo "FAIL: missing dist/client/index.html — build failed"; exit 1; }

echo ">>> rsync dist/client/ → $VOX_DASH_DIST"
sudo mkdir -p "$VOX_DASH_DIST"
sudo rsync -a --delete --exclude='.user.ini' dist/client/ "$VOX_DASH_DIST/"

echo ">>> Restart dashboard preview (:5175) + API"
cd "$ROOT"
bash ./vox.sh restart || true

echo ""
echo "=== Verify ==="
grep -oE '/assets/[^"]+\.(js|css)' "$VOX_DASH_DIST/index.html" | head -3 || true
if grep -q 'tabler-icons' "$VOX_DASH_DIST/index.html" 2>/dev/null; then
  echo "FAIL: still OLD dashboard theme (tabler-icons) — check nginx root points to $VOX_DASH_DIST"
  exit 1
fi
echo "OK — hard refresh: Ctrl+Shift+R on https://dashboard.voxbulk.com/"
echo "    Create survey: /surveys/new"
