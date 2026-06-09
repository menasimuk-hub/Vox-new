#!/usr/bin/env bash
# Pull latest code + rebuild + publish CUSTOMER dashboard only (dashboard.voxbulk.com).
#
# WARNING: Admin UI is NOT updated. Use scripts/vps-sync-all-ui.sh or ./deploy-vps.sh instead.
#
# GitHub push does NOT update the live site — run this ON THE VPS.
#
# Usage:
#   cd /www/voxbulk
#   VOX_GIT_BRANCH=fix/wa-interview-platform-templates bash scripts/vps-sync-dashboard.sh
#
# Skip git pull (rebuild current tree only):
#   VOX_SKIP_GIT=1 bash scripts/vps-sync-dashboard.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"
VOX_DASH_DIST="${VOX_DASH_DIST:-/www/wwwroot/dashboard.voxbulk.com}"
DEPLOY_LOG="${VOX_DEPLOY_LOG:-/tmp/voxbulk-deploy.log}"

# shellcheck source=lib/vps-git-sync.sh
source "$ROOT/scripts/lib/vps-git-sync.sh"

exec > >(tee -a "$DEPLOY_LOG") 2>&1

on_fail() {
  vox_print_deploy_banner FAILED "$ROOT"
  exit 1
}
trap on_fail ERR

echo "=== VoxBulk dashboard-only sync ==="
echo "WARN: Admin UI will stay stale — prefer: bash scripts/vps-sync-all-ui.sh"
echo "Repo:    $ROOT"
echo "Wwwroot: $VOX_DASH_DIST"
echo "Branch:  ${VOX_GIT_BRANCH:-$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"
echo ""

vox_git_sync "$ROOT"

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
vox_verify_build_info_sha "$ROOT" "$VOX_DASH_DIST" "dashboard"

if grep -q 'tabler-icons' "$VOX_DASH_DIST/index.html" 2>/dev/null; then
  echo "FAIL: still OLD dashboard theme (tabler-icons) — check nginx root points to $VOX_DASH_DIST"
  exit 1
fi

echo "Dashboard build-info.json:"
cat "$VOX_DASH_DIST/build-info.json"

trap - ERR
vox_print_deploy_banner COMPLETE "$ROOT"
