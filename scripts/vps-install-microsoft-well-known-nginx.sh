#!/usr/bin/env bash
# One-time VPS fix: serve Microsoft Entra publisher-domain file from wwwroot.
# Run on the VPS as deploy user (uses sudo for nginx + wwwroot):
#   cd /www/voxbulk && bash scripts/vps-install-microsoft-well-known-nginx.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_DIR="$ROOT/voxbulk.com/frontend"
VOX_PUBLIC_DIST="${VOX_PUBLIC_DIST:-/www/wwwroot/voxbulk.com}"
NGINX_VHOST="${VOX_NGINX_VHOST:-/www/server/panel/vhost/nginx/voxbulk.com.conf}"
WELL_KNOWN_SNIPPET="$ROOT/docs/nginx-well-known-microsoft-voxbulk.com.conf"
BAOTA_INCLUDE="/www/server/panel/vhost/nginx/well-known/voxbulk.com-microsoft.conf"

echo "=== Microsoft .well-known nginx + file install ==="

src="$PUBLIC_DIR/public/.well-known/microsoft-identity-association.json"
dest_dir="$VOX_PUBLIC_DIST/.well-known"
dest="$dest_dir/microsoft-identity-association.json"

[[ -f "$src" ]] || { echo "Missing $src — git pull first"; exit 1; }

sudo mkdir -p "$dest_dir"
sudo cp -a "$src" "$dest"
echo "Installed $dest"

if [[ -f "$NGINX_VHOST" ]] && grep -q 'location ~ \\.well-known' "$NGINX_VHOST" 2>/dev/null; then
  echo "WARNING: $NGINX_VHOST still has 'location ~ \\.well-known' — that block returns 404."
  echo "Replace it using docs/nginx-voxbulk.com.conf or install the Baota snippet below."
fi

if [[ -f "$WELL_KNOWN_SNIPPET" ]]; then
  sudo cp -a "$WELL_KNOWN_SNIPPET" "$BAOTA_INCLUDE"
  echo "Installed nginx snippet → $BAOTA_INCLUDE"
  echo "Ensure voxbulk.com vhost includes: include /www/server/panel/vhost/nginx/well-known/voxbulk.com.conf;"
  echo "(Baota merges well-known/*.conf there, or paste location block into the main vhost.)"
fi

if command -v nginx >/dev/null 2>&1; then
  sudo nginx -t
  sudo nginx -s reload
fi

code=$(curl -s -o /dev/null -w "%{http_code}" "https://voxbulk.com/.well-known/microsoft-identity-association.json" || echo "000")
echo "HTTPS check: https://voxbulk.com/.well-known/microsoft-identity-association.json → HTTP $code"
if [[ "$code" != "200" ]]; then
  echo "If not 200, edit $NGINX_VHOST — use location ^~ /.well-known/ alias from docs/nginx-voxbulk.com.conf"
  exit 1
fi
echo "OK — retry publisher domain verification in Microsoft Entra."
