#!/usr/bin/env bash
# One-time VPS: nginx rate limits for api.voxbulk.com (aaPanel, no Cloudflare).
# Run on the server:
#   cd /www/voxbulk && git pull origin main && sudo bash scripts/vps-install-api-nginx-limits.sh
set -euo pipefail

NGINX_CONF="${VOX_NGINX_CONF:-/www/server/nginx/conf/nginx.conf}"
ZONE_INCLUDE="${VOX_API_LIMIT_INCLUDE:-/www/server/nginx/conf/voxbulk-api-limits.conf}"
NGINX_VHOST="${VOX_NGINX_VHOST:-/www/server/panel/vhost/nginx/api.voxbulk.com.conf}"

echo "=== API nginx limit_req install ==="

if [[ ! -f "$NGINX_VHOST" ]]; then
  echo "Missing API vhost: $NGINX_VHOST"
  exit 1
fi

sudo tee "$ZONE_INCLUDE" >/dev/null <<'EOF'
# VoxBulk API edge throttles — managed by vps-install-api-nginx-limits.sh
# Real client IP is $remote_addr (nginx, no Cloudflare).
limit_req_zone $binary_remote_addr zone=auth_public:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=api_general:20m rate=50r/s;
limit_req_zone $binary_remote_addr zone=webhooks:10m rate=40r/s;
EOF
echo "Wrote $ZONE_INCLUDE"

if ! grep -q 'voxbulk-api-limits.conf' "$NGINX_CONF" 2>/dev/null \
  && ! grep -q 'zone=auth_public' "$NGINX_CONF" 2>/dev/null; then
  tmp="$(mktemp)"
  python3 - "$NGINX_CONF" "$tmp" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])
out = Path(sys.argv[2])
text = src.read_text(encoding="utf-8")
line = "        include /www/server/nginx/conf/voxbulk-api-limits.conf;\n"
if "voxbulk-api-limits.conf" in text or "zone=auth_public" in text:
    out.write_text(text, encoding="utf-8")
    print("already present")
    raise SystemExit(0)
idx = text.rfind("voxbulk-smart-card-limit.conf")
if idx >= 0:
    nl = text.find("\n", idx)
    text = text[: nl + 1] + line + text[nl + 1 :]
else:
    idx = text.rfind("limit_conn_zone")
    if idx >= 0:
        nl = text.find("\n", idx)
        text = text[: nl + 1] + line + text[nl + 1 :]
    else:
        marker = "include /www/server/panel/vhost/nginx/*.conf;"
        if marker not in text:
            raise SystemExit("Could not find insertion point in nginx.conf")
        text = text.replace(marker, line + marker, 1)
out.write_text(text, encoding="utf-8")
print("patched")
PY
  sudo cp -a "$tmp" "$NGINX_CONF"
  rm -f "$tmp"
  echo "Patched $NGINX_CONF to include API zone file"
else
  echo "nginx.conf already references auth_public / API zone file — skip"
fi

echo "Patching $NGINX_VHOST …"
sudo cp -a "$NGINX_VHOST" "${NGINX_VHOST}.bak.api-limits-$(date +%Y%m%d%H%M%S)"
tmp="$(mktemp)"
python3 - "$NGINX_VHOST" "$tmp" <<'PY'
from pathlib import Path
import sys

vhost = Path(sys.argv[1])
out = Path(sys.argv[2])
text = vhost.read_text(encoding="utf-8")

proxy = """
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
"""

auth_block = f"""
    # Password / register / OAuth start — 10 r/s burst 20 (no Cloudflare).
    location ^~ /auth/ {{
        limit_req zone=auth_public burst=20 nodelay;
        limit_req_status 429;
{proxy}    }}
"""

wh_block = f"""
    location ^~ /webhooks/ {{
        limit_req zone=webhooks burst=80 nodelay;
        limit_req_status 429;
{proxy}    }}
"""

telnyx_block = f"""
    location ^~ /telnyx/webhooks/ {{
        limit_req zone=webhooks burst=80 nodelay;
        limit_req_status 429;
{proxy}    }}
"""

marker = "    location / {"
if marker not in text:
    raise SystemExit("Could not find '    location / {' in API vhost")

if "zone=auth_public" not in text:
    text = text.replace(marker, auth_block + "\n" + marker, 1)
if "location ^~ /webhooks/" not in text:
    text = text.replace(marker, wh_block + "\n" + marker, 1)
if "location ^~ /telnyx/webhooks/" not in text:
    text = text.replace(marker, telnyx_block + "\n" + marker, 1)

if "zone=api_general" not in text:
    text = text.replace(
        marker,
        "    location / {\n        limit_req zone=api_general burst=100 nodelay;\n        limit_req_status 429;",
        1,
    )

out.write_text(text, encoding="utf-8")
print("patched")
PY
sudo cp -a "$tmp" "$NGINX_VHOST"
rm -f "$tmp"

echo "Testing nginx config…"
sudo nginx -t
sudo nginx -s reload || sudo systemctl reload nginx
echo "OK — auth/api/webhook limit_req active on api.voxbulk.com"
echo "Smoke: hammer POST https://api.voxbulk.com/auth/token until 429. Webhooks should still retry within burst=80."
