#!/usr/bin/env bash
# Rebuild + publish admin + dashboard (+ build public preview bundle).
# No git pull, no migrations. Run ON THE VPS after git pull when UI is stale.
#
# Full deploy (git + migrate + all builds): ./deploy-vps.sh
# Dashboard only (git pull + build + rsync): bash scripts/vps-sync-dashboard.sh
# Public marketing site is served via vite preview (vox.sh), not static wwwroot.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADMIN_DIR="$ROOT/admin.voxbulk.com/adim-web"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
VOX_ADMIN_DIST="${VOX_ADMIN_DIST:-/www/wwwroot/admin.voxbulk.com}"
VOX_DASH_DIST="${VOX_DASH_DIST:-/www/wwwroot/dashboard.voxbulk.com}"

echo "=== VoxBulk UI-only deploy (no git pull) ==="
echo "WARN: This script does NOT pull from GitHub. Run git pull first, or use scripts/vps-sync-all-ui.sh"
echo "Git: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '?') @ $(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
echo "Admin wwwroot: $VOX_ADMIN_DIST"
echo "Dashboard wwwroot: $VOX_DASH_DIST"
echo ""

if [[ -f "$ROOT/scripts/sync-brand-assets.mjs" ]]; then
  node "$ROOT/scripts/sync-brand-assets.mjs"
fi

build() {
  local dir="$1"
  local name="$2"
  echo ">>> Building $name …"
  cd "$dir"
  npm install
  npm run build
}

rsync_dist() {
  local src="$1"
  local dest="$2"
  local label="$3"
  [[ -f "$src/index.html" ]] || { echo "FAIL: missing $src/index.html"; exit 1; }
  echo ">>> Rsync $label → $dest"
  sudo mkdir -p "$dest"
  sudo rsync -a --delete --exclude='.user.ini' "$src/" "$dest/"
}

build "$ADMIN_DIR" "admin"
build "$DASH_DIR" "dashboard"
if [[ -d "$PUBLIC_DIR" ]]; then
  build "$PUBLIC_DIR" "public site"
else
  echo ">>> Skip public site (not found at $PUBLIC_DIR)"
fi

rsync_dist "$ADMIN_DIR/dist" "$VOX_ADMIN_DIST" "admin dist"
rsync_dist "$DASH_DIR/dist/client" "$VOX_DASH_DIST" "dashboard dist/client"

echo ""
echo ">>> Restart preview + API (serves dashboard on :5175 if nginx proxies there)"
cd "$ROOT"
bash ./vox.sh restart || true

echo ""
echo "=== Verify ==="
echo "Dashboard index:"
grep -oE '/assets/[^"]+\.(js|css)' "$VOX_DASH_DIST/index.html" | head -3 || true
if grep -q 'tabler-icons' "$VOX_DASH_DIST/index.html" 2>/dev/null; then
  echo "FAIL: dashboard still OLD theme (tabler-icons in index.html)"
  exit 1
fi
# shellcheck source=lib/vps-git-sync.sh
source "$ROOT/scripts/lib/vps-git-sync.sh"
if [[ -f "$VOX_DASH_DIST/build-info.json" ]]; then
  vox_verify_build_info_sha "$ROOT" "$VOX_DASH_DIST" "dashboard" || {
    echo "FAIL: build-info SHA mismatch — git pull may not have run before this script"
    exit 1
  }
  echo "Dashboard build-info.json:"
  cat "$VOX_DASH_DIST/build-info.json"
fi

echo "OK — hard refresh browser: Ctrl+Shift+R"
