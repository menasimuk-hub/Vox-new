#!/usr/bin/env bash
# One-time VPS: serve voxbulk.com from static wwwroot (like dashboard). Stop vite preview :5173.
# Run AFTER a deploy that rsynced dist/client → /www/wwwroot/voxbulk.com
#
#   cd /www/voxbulk && git pull origin main && ./deploy-vps.sh
#   sudo bash scripts/vps-install-public-static-nginx.sh
set -euo pipefail

WWWROOT="${VOX_PUBLIC_DIST:-/www/wwwroot/voxbulk.com}"
NGINX_VHOST="${VOX_PUBLIC_VHOST:-/www/server/panel/vhost/nginx/voxbulk.com.conf}"
API_UPSTREAM="voxbulk_api"
if ! grep -q 'upstream voxbulk_api' /www/server/nginx/conf/nginx.conf 2>/dev/null \
  && ! grep -q 'voxbulk-api-upstream.conf' /www/server/nginx/conf/nginx.conf 2>/dev/null; then
  API_UPSTREAM="127.0.0.1:8000"
fi

echo "=== Public site static wwwroot ==="

[[ "$(id -u)" -eq 0 ]] || { echo "Run with sudo"; exit 1; }
[[ -f "$NGINX_VHOST" ]] || { echo "Missing public vhost: $NGINX_VHOST"; exit 1; }

if [[ ! -f "$WWWROOT/index.html" ]]; then
  echo "Missing $WWWROOT/index.html — rsync public dist/client first (./deploy-vps.sh)"
  exit 1
fi

if grep -q 'try_files \$uri \$uri/ /index.html' "$NGINX_VHOST" 2>/dev/null \
  && grep -q "root $WWWROOT" "$NGINX_VHOST" 2>/dev/null \
  && ! grep -q '127.0.0.1:5173' "$NGINX_VHOST" 2>/dev/null; then
  echo "vhost already static — skip patch"
else
  echo "Patching $NGINX_VHOST → static SPA + /frontpage/ proxy …"
  sudo cp -a "$NGINX_VHOST" "${NGINX_VHOST}.bak.public-static-$(date +%Y%m%d%H%M%S)"
  tmp="$(mktemp)"
  python3 - "$NGINX_VHOST" "$tmp" "$WWWROOT" "$API_UPSTREAM" <<'PY'
from pathlib import Path
import re
import sys

vhost = Path(sys.argv[1])
out = Path(sys.argv[2])
wwwroot = sys.argv[3]
upstream = sys.argv[4]
text = vhost.read_text(encoding="utf-8")

proxy_headers = """
        proxy_http_version 1.1;
        proxy_set_header Host api.voxbulk.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        client_max_body_size 20m;
        proxy_next_upstream error timeout http_502 http_503;
        proxy_next_upstream_tries 2;
"""

static_locations = f"""
    root {wwwroot};
    index index.html;

    location = /robots.txt {{
        proxy_pass http://{upstream}/frontpage/seo/robots-plain;
{proxy_headers}    }}

    location = /sitemap.xml {{
        proxy_pass http://{upstream}/frontpage/seo/sitemap.xml;
{proxy_headers}    }}

    location = /news-sitemap.xml {{
        proxy_pass http://{upstream}/frontpage/seo/news-sitemap.xml;
{proxy_headers}    }}

    location ^~ /frontpage/ {{
        proxy_pass http://{upstream};
{proxy_headers}    }}

    location / {{
        try_files $uri $uri/ $uri/index.html /index.html;
    }}

    location ~ .*\\.(gif|jpg|jpeg|png|bmp|swf|ico|webp|svg)$ {{
        expires 30d;
        access_log off;
    }}

    location ~ .*\\.(js|css|woff2?|ttf|eot)$ {{
        expires 12h;
        access_log off;
    }}
"""

# Drop the vite preview proxy block (location / { proxy_pass :5173 ... }).
text = re.sub(
    r"\n\s*# TanStack app[^\n]*\n\s*location /\s*\{[\s\S]*?proxy_pass http://127\.0\.0\.1:5173;[\s\S]*?\n\s*\}\s*",
    "\n" + static_locations + "\n",
    text,
    count=1,
)
if "127.0.0.1:5173" in text:
    # Fallback: any remaining preview proxy.
    text = re.sub(
        r"\n\s*location /\s*\{[\s\S]*?proxy_pass http://127\.0\.0\.1:5173;[\s\S]*?\n\s*\}\s*",
        "\n" + static_locations + "\n",
        text,
        count=1,
    )

if "try_files $uri $uri/ /index.html" not in text:
    raise SystemExit("Could not replace vite preview location / — edit vhost by hand using docs/nginx-voxbulk.com.conf")

# Ensure root is set if the regex inserted locations without a prior root.
if f"root {wwwroot}" not in text:
    text = text.replace("    index index.html;", f"    index index.html;\n    root {wwwroot};", 1)

out.write_text(text, encoding="utf-8")
print("patched")
PY
  sudo cp -a "$tmp" "$NGINX_VHOST"
  rm -f "$tmp"
fi

echo "Testing nginx config…"
nginx -t
nginx -s reload || systemctl reload nginx

if [[ -f /etc/systemd/system/voxbulk-public.service ]]; then
  echo "Disabling vite preview unit voxbulk-public …"
  systemctl disable --now voxbulk-public.service 2>/dev/null || true
fi
pkill -f "vite preview.*5173" 2>/dev/null || true
pkill -f "npm run preview.*5173" 2>/dev/null || true

echo "OK — https://voxbulk.com is static wwwroot"
echo "Smoke: curl -sI https://voxbulk.com | head -5"
echo "       curl -sI https://voxbulk.com/sitemap.xml | head -5"
echo "       curl -s https://voxbulk.com/frontpage/faq | head -c 80"
