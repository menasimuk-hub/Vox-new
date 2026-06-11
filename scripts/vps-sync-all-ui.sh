#!/usr/bin/env bash
# Pull latest code + rebuild + publish ALL static UIs (admin + dashboard).
# Run ON THE VPS after every GitHub push.
#
# Usage:
#   cd /www/voxbulk
#   VOX_GIT_BRANCH=fix/admin-finance-hardening bash scripts/vps-sync-all-ui.sh
#
# Skip git pull (rebuild current tree only):
#   VOX_SKIP_GIT=1 bash scripts/vps-sync-all-ui.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADMIN_DIR="$ROOT/admin.voxbulk.com/adim-web"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
VOX_ADMIN_DIST="${VOX_ADMIN_DIST:-/www/wwwroot/admin.voxbulk.com}"
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

echo "=== VoxBulk full UI sync (admin + dashboard) ==="
echo "Repo:    $ROOT"
echo "Admin:   $VOX_ADMIN_DIST"
echo "Dash:    $VOX_DASH_DIST"
echo "Branch:  ${VOX_GIT_BRANCH:-$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"
echo ""

vox_git_sync "$ROOT"

if [[ -f "$ROOT/scripts/sync-brand-assets.mjs" ]]; then
  node "$ROOT/scripts/sync-brand-assets.mjs"
fi

build_app() {
  local dir="$1"
  local name="$2"
  echo ">>> npm install + build ($name)"
  cd "$dir"
  npm install
  npm run build
}

rsync_dist() {
  local src="$1"
  local dest="$2"
  local label="$3"
  [[ -f "$src/index.html" ]] || { echo "FAIL: missing $src/index.html ($label)"; exit 1; }
  echo ">>> rsync $label → $dest"
  sudo mkdir -p "$dest"
  sudo rsync -a --delete --exclude='.user.ini' "$src/" "$dest/"
}

build_app "$ADMIN_DIR" "admin"
build_app "$DASH_DIR" "dashboard"
if [[ -d "$PUBLIC_DIR" ]]; then
  build_app "$PUBLIC_DIR" "public site"
else
  echo ">>> Skip public site (not found)"
fi

rsync_dist "$ADMIN_DIR/dist" "$VOX_ADMIN_DIST" "admin"
rsync_dist "$DASH_DIR/dist/client" "$VOX_DASH_DIST" "dashboard"

echo ">>> Restart services"
cd "$ROOT"
bash ./vox.sh restart || true

echo ""
echo "=== Verify deployed SHA ==="
vox_verify_build_info_sha "$ROOT" "$VOX_DASH_DIST" "dashboard"
if [[ -f "$VOX_ADMIN_DIST/build-info.json" ]]; then
  vox_verify_build_info_sha "$ROOT" "$VOX_ADMIN_DIST" "admin"
fi

if grep -q 'tabler-icons' "$VOX_DASH_DIST/index.html" 2>/dev/null; then
  echo "FAIL: dashboard still OLD theme (tabler-icons) — check nginx root: $VOX_DASH_DIST"
  exit 1
fi

echo ""
echo "Dashboard build-info.json:"
cat "$VOX_DASH_DIST/build-info.json"

trap - ERR
vox_print_deploy_banner COMPLETE "$ROOT"
