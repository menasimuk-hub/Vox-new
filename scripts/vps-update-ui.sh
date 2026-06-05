#!/usr/bin/env bash
# Rebuild + publish admin + dashboard only (no git pull, no migrations).
# Run ON THE VPS after git pull, or when static sites are stale.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADMIN_DIR="$ROOT/admin.voxbulk.com/adim-web"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"
VOX_ADMIN_DIST="${VOX_ADMIN_DIST:-/www/wwwroot/admin.voxbulk.com}"
VOX_DASH_DIST="${VOX_DASH_DIST:-/www/wwwroot/dashboard.voxbulk.com}"

echo "=== VoxBulk UI-only deploy ==="
echo "Git: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
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
echo "OK — hard refresh browser: Ctrl+Shift+R"
