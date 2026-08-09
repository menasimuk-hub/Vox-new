#!/usr/bin/env bash
# One-time VPS: nginx rate limit for public Smart Card API paths (aaPanel, no Cloudflare).
# Run on the VPS:
#   cd /www/voxbulk && git pull origin main && sudo bash scripts/vps-install-smart-card-nginx-limit.sh
set -euo pipefail

NGINX_CONF="${VOX_NGINX_CONF:-/www/server/nginx/conf/nginx.conf}"
ZONE_INCLUDE="${VOX_SC_LIMIT_INCLUDE:-/www/server/nginx/conf/voxbulk-smart-card-limit.conf}"
NGINX_VHOST="${VOX_NGINX_VHOST:-/www/server/panel/vhost/nginx/api.voxbulk.com.conf}"

echo "=== Smart Card nginx limit_req install ==="

if [[ ! -f "$NGINX_VHOST" ]]; then
  echo "Missing API vhost: $NGINX_VHOST"
  exit 1
fi

# 1) http-level zone (include file)
if [[ ! -f "$ZONE_INCLUDE" ]] || ! grep -q 'zone=sc_public' "$ZONE_INCLUDE" 2>/dev/null; then
  sudo tee "$ZONE_INCLUDE" >/dev/null <<'EOF'
# VoxBulk Smart Card public scrape throttle (API edge) — managed by vps-install-smart-card-nginx-limit.sh
limit_req_zone $binary_remote_addr zone=sc_public:10m rate=30r/s;
EOF
  echo "Wrote $ZONE_INCLUDE"
else
  echo "Zone include already present — skip write"
fi

if ! grep -q 'voxbulk-smart-card-limit.conf' "$NGINX_CONF" 2>/dev/null; then
  if grep -qE '^\s*http\s*\{' "$NGINX_CONF"; then
    tmp="$(mktemp)"
    # Insert include just after `http {`
    awk '
      BEGIN { done=0 }
      /^\s*http\s*\{/ && !done {
        print
        print "    include /www/server/nginx/conf/voxbulk-smart-card-limit.conf;"
        done=1
        next
      }
      { print }
    ' "$NGINX_CONF" >"$tmp"
    sudo cp -a "$tmp" "$NGINX_CONF"
    rm -f "$tmp"
    echo "Patched $NGINX_CONF to include zone file"
  else
    echo "WARNING: could not find http { in $NGINX_CONF — add manually:"
    echo "  include /www/server/nginx/conf/voxbulk-smart-card-limit.conf;"
  fi
else
  echo "nginx.conf already includes zone file — skip"
fi

# 2) location on api.voxbulk.com
if grep -q 'location ^~ /public/smart-card/' "$NGINX_VHOST" 2>/dev/null; then
  echo "Vhost already has Smart Card location — skip patch"
else
  echo "Patching $NGINX_VHOST …"
  sudo cp -a "$NGINX_VHOST" "${NGINX_VHOST}.bak.sc-limit-$(date +%Y%m%d%H%M%S)"
  tmp="$(mktemp)"
  python3 - "$NGINX_VHOST" "$tmp" <<'PY'
from pathlib import Path
import sys

vhost = Path(sys.argv[1])
out = Path(sys.argv[2])
text = vhost.read_text(encoding="utf-8")
block = """
    location ^~ /public/smart-card/ {
        limit_req zone=sc_public burst=60 nodelay;
        limit_req_status 429;
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host api.voxbulk.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        client_max_body_size 50m;
    }
"""
marker = "    location / {"
if marker not in text:
    raise SystemExit("Could not find '    location / {' in API vhost")
if "location ^~ /public/smart-card/" not in text:
    text = text.replace(marker, block + "\n" + marker, 1)
out.write_text(text, encoding="utf-8")
print("patched")
PY
  sudo cp -a "$tmp" "$NGINX_VHOST"
  rm -f "$tmp"
fi

echo "Testing nginx config…"
sudo nginx -t
sudo nginx -s reload || sudo systemctl reload nginx
echo "OK — Smart Card limit_req active on api.voxbulk.com"
echo "Smoke: hammer curl to /public/smart-card/{token}/reveal until 429; phone scan should still work."
