#!/usr/bin/env bash
# Run ON THE VPS: bash scripts/vps-verify-dashboard.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WWWROOT="/www/wwwroot/dashboard.voxbulk.com"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"

echo "=== Dashboard deploy check ==="
echo "Git: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
echo ""

if [[ ! -f "$WWWROOT/index.html" ]]; then
  echo "[FAIL] No $WWWROOT/index.html"
  echo "Fix: cd $DASH_DIR && npm run build"
  echo "     sudo rsync -a --delete dist/client/ $WWWROOT/"
  exit 1
fi

if grep -q 'tabler-icons' "$WWWROOT/index.html"; then
  echo "[FAIL] OLD dashboard theme in wwwroot (tabler-icons)"
  echo "Fix: pull latest, npm run build, rsync dist/client/ (NOT dist/)"
  exit 1
fi

echo "[OK] index.html looks like NEW dashboard (no tabler-icons)"
grep -oE '/assets/[^"]+\.(js|css)' "$WWWROOT/index.html" | head -3

if [[ -f "$DASH_DIR/dist/client/index.html" ]]; then
  if grep -q 'tabler-icons' "$DASH_DIR/dist/client/index.html" 2>/dev/null; then
    echo "[WARN] Repo build is old — git pull && npm run build"
  else
    echo "[OK] Repo dist/client matches new theme — rsync if wwwroot is stale"
  fi
else
  echo "[WARN] No build yet: cd $DASH_DIR && npm run build"
fi

echo ""
echo "Deploy command:"
echo "  cd $DASH_DIR && npm run build"
echo "  sudo rsync -a --delete --exclude='.user.ini' dist/client/ $WWWROOT/"
