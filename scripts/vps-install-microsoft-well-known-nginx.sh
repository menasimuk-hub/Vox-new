#!/usr/bin/env bash
# One-time VPS fix: Microsoft Entra publisher-domain file + nginx alias.
# Run on the VPS:
#   cd /www/voxbulk && git pull origin main && bash scripts/vps-install-microsoft-well-known-nginx.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
VOX_PUBLIC_DIST="${VOX_PUBLIC_DIST:-/www/wwwroot/voxbulk.com}"
NGINX_VHOST="${VOX_NGINX_VHOST:-/www/server/panel/vhost/nginx/voxbulk.com.conf}"

WELL_KNOWN_BLOCK='    location ^~ /.well-known/ {
        alias /www/wwwroot/voxbulk.com/.well-known/;
        default_type application/json;
        add_header Cache-Control "public, max-age=300";
        allow all;
    }'

echo "=== Microsoft .well-known nginx + file install ==="

src="$PUBLIC_DIR/public/.well-known/microsoft-identity-association.json"
dest_dir="$VOX_PUBLIC_DIST/.well-known"
dest="$dest_dir/microsoft-identity-association.json"

[[ -f "$src" ]] || { echo "Missing $src — run: git pull origin main"; exit 1; }

sudo mkdir -p "$dest_dir"
sudo cp -a "$src" "$dest"
echo "Installed $dest"
sudo cat "$dest"

[[ -f "$NGINX_VHOST" ]] || { echo "Missing nginx vhost: $NGINX_VHOST"; exit 1; }

if grep -q 'location \^~ /\.well-known/' "$NGINX_VHOST" 2>/dev/null; then
  echo "nginx already has location ^~ /.well-known/ — skip vhost patch"
else
  echo "Patching $NGINX_VHOST …"
  tmp="$(mktemp)"
  python3 - "$NGINX_VHOST" "$tmp" <<'PY'
import re
import sys
from pathlib import Path

vhost = Path(sys.argv[1])
out = Path(sys.argv[2])
text = vhost.read_text(encoding="utf-8")

new_block = """    location ^~ /.well-known/ {
        alias /www/wwwroot/voxbulk.com/.well-known/;
        default_type application/json;
        add_header Cache-Control "public, max-age=300";
        allow all;
    }"""

# Remove broken block that matches .well-known but never serves files.
text, n_removed = re.subn(
    r"\n\s*location ~ \\.well-known\s*\{\s*\n\s*allow all;\s*\n\s*\}\s*",
    "\n",
    text,
    count=1,
)

if "location ^~ /.well-known/" not in text:
    marker = "    location / {"
    if marker not in text:
        raise SystemExit("Could not find 'location / {' in nginx vhost — edit manually using docs/nginx-voxbulk.com.conf")
    text = text.replace(marker, new_block + "\n\n" + marker, 1)

out.write_text(text, encoding="utf-8")
print(f"patched (removed_old_well_known={bool(n_removed)})")
PY
  sudo cp -a "$tmp" "$NGINX_VHOST"
  rm -f "$tmp"
  echo "Updated $NGINX_VHOST"
fi

if command -v nginx >/dev/null 2>&1; then
  sudo nginx -t
  sudo nginx -s reload
  echo "nginx reloaded"
fi

echo ""
code=$(curl -s -o /dev/null -w "%{http_code}" "https://voxbulk.com/.well-known/microsoft-identity-association.json" || echo "000")
body=$(curl -s "https://voxbulk.com/.well-known/microsoft-identity-association.json" || true)
echo "HTTPS: https://voxbulk.com/.well-known/microsoft-identity-association.json → HTTP $code"
echo "$body" | head -5

if [[ "$code" != "200" ]] || ! grep -q 'ac71bc98-dbfb-462f-ac55-22883092eede' <<<"$body"; then
  echo ""
  echo "Still failing. In Baota → Website → voxbulk.com → Config, replace:"
  echo "  location ~ \\.well-known { allow all; }"
  echo "with the block from docs/nginx-voxbulk.com.conf (location ^~ /.well-known/ … alias …)"
  exit 1
fi

echo ""
echo "OK — retry publisher domain verification in Microsoft Entra."
