#!/usr/bin/env bash
# Run ON THE VPS from repo root: bash scripts/vps-verify-dashboard.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NGINX_CONF="/www/server/panel/vhost/nginx/dashboard.voxbulk.com.conf"
WWWROOT="/www/wwwroot/dashboard.voxbulk.com"
DASH_DIR="$ROOT/dashboard.voxbulk.com/dashboard-web"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
bad()  { echo -e "${RED}[fail]${NC} $*"; }

echo "=== VoxBulk dashboard VPS check ==="
echo "Repo: $ROOT"
echo ""

cd "$ROOT"
COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
echo "Git commit: $COMMIT (want e7d8389 or newer on main)"
echo ""

# 1) Node dashboard preview
if curl -sf -o /dev/null --max-time 5 http://127.0.0.1:5175/ 2>/dev/null; then
  ok "Dashboard Node app responds on http://127.0.0.1:5175/"
  PREVIEW=$(curl -s --max-time 8 http://127.0.0.1:5175/ 2>/dev/null | head -c 4000 || true)
  if echo "$PREVIEW" | grep -q 'tabler-icons'; then
    bad "Port 5175 is serving OLD dashboard (tabler-icons found)"
  elif echo "$PREVIEW" | grep -qi 'VoxBulk Dashboard\|tanstack\|__vite'; then
    ok "Port 5175 looks like NEW dashboard"
  else
    warn "Could not confirm theme on :5175 (check manually)"
  fi
else
  bad "Nothing on http://127.0.0.1:5175/ — run: cd $ROOT && ./vox.sh restart"
  warn "Log: tail -50 /tmp/voxbulk-dashboard.log"
fi

echo ""

# 2) Nginx config
if [[ -f "$NGINX_CONF" ]]; then
  if grep -q 'proxy_pass.*127.0.0.1:5175' "$NGINX_CONF"; then
    ok "Nginx proxies dashboard → 127.0.0.1:5175"
  else
    bad "Nginx does NOT proxy to :5175 — still static wwwroot mode"
    warn "Fix: sudo cp $ROOT/docs/nginx-dashboard.voxbulk.com.conf $NGINX_CONF"
    warn "Then: sudo nginx -t && sudo nginx -s reload"
  fi
  if grep -qE '^\s*root\s+/www/wwwroot/dashboard' "$NGINX_CONF"; then
    warn "Nginx still has 'root /www/wwwroot/dashboard...' — remove it when using proxy"
  fi
else
  warn "Nginx config not found at $NGINX_CONF (path may differ on your panel)"
fi

echo ""

# 3) Static wwwroot (old dashboard)
if [[ -d "$WWWROOT" ]]; then
  COUNT=$(find "$WWWROOT" -maxdepth 2 -type f 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$COUNT" -gt 0 ]]; then
    if [[ -f "$WWWROOT/index.html" ]] && grep -q 'tabler-icons' "$WWWROOT/index.html" 2>/dev/null; then
      bad "OLD dashboard static files still in $WWWROOT ($COUNT files)"
      warn "If nginx uses 'root' here, browser shows OLD orange theme"
      warn "Use nginx PROXY to :5175 instead; wwwroot can stay empty"
    else
      warn "wwwroot has $COUNT file(s) — ensure nginx is not serving them as root"
    fi
  else
    ok "wwwroot is empty (good if nginx proxies to :5175)"
  fi
fi

echo ""

# 4) Build freshness
if [[ -d "$DASH_DIR/dist/client" ]]; then
  ok "dashboard-web dist exists ($(stat -c %y "$DASH_DIR/dist/client" 2>/dev/null || stat -f %Sm "$DASH_DIR/dist/client" 2>/dev/null || echo built))"
else
  bad "No dashboard build — run: cd $DASH_DIR && npm run build"
fi

echo ""
echo "=== Browser quick test ==="
echo "View source on https://dashboard.voxbulk.com/"
echo "  OLD theme: tabler-icons CDN, title 'VoxBulk — App Dashboard'"
echo "  NEW theme: 'VoxBulk Dashboard', beige/shadcn UI, no tabler-icons"
echo ""
echo "=== Fix (run on VPS) ==="
cat <<'FIX'
cd /www/voxbulk
git fetch voxnew main && git reset --hard voxnew/main
cd dashboard.voxbulk.com/dashboard-web && npm install && npm run build
cd /www/voxbulk
sudo cp docs/nginx-dashboard.voxbulk.com.conf /www/server/panel/vhost/nginx/dashboard.voxbulk.com.conf
sudo nginx -t && sudo nginx -s reload
./vox.sh restart
bash scripts/vps-verify-dashboard.sh
FIX
