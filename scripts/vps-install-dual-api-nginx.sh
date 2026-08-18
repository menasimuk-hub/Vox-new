#!/usr/bin/env bash
# One-time VPS: nginx upstream for dual gunicorn (:8000 + :8001).
# Start API B first, then switch proxy_pass so traffic never hits a missing backend.
#
#   cd /www/voxbulk && git pull origin main
#   sudo bash scripts/vps-setup-api-systemd.sh
#   sudo bash scripts/vps-install-dual-api-nginx.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NGINX_CONF="${VOX_NGINX_CONF:-/www/server/nginx/conf/nginx.conf}"
UPSTREAM_INCLUDE="${VOX_API_UPSTREAM_INCLUDE:-/www/server/nginx/conf/voxbulk-api-upstream.conf}"
NGINX_VHOST="${VOX_NGINX_VHOST:-/www/server/panel/vhost/nginx/api.voxbulk.com.conf}"

echo "=== Dual API nginx upstream ==="

if [[ ! -f "$NGINX_VHOST" ]]; then
  echo "Missing API vhost: $NGINX_VHOST"
  exit 1
fi

[[ "$(id -u)" -eq 0 ]] || { echo "Run with sudo"; exit 1; }

sudo tee "$UPSTREAM_INCLUDE" >/dev/null <<'EOF'
# VoxBulk dual gunicorn — managed by vps-install-dual-api-nginx.sh
# Reload A then B on deploy; nginx skips a dead port (max_fails).
upstream voxbulk_api {
    server 127.0.0.1:8000 max_fails=1 fail_timeout=10s;
    server 127.0.0.1:8001 max_fails=1 fail_timeout=10s;
}
EOF
echo "Wrote $UPSTREAM_INCLUDE"

if ! grep -q 'voxbulk-api-upstream.conf' "$NGINX_CONF" 2>/dev/null \
  && ! grep -q 'upstream voxbulk_api' "$NGINX_CONF" 2>/dev/null; then
  tmp="$(mktemp)"
  python3 - "$NGINX_CONF" "$tmp" <<'PY'
from pathlib import Path
import sys

src = Path(sys.argv[1])
out = Path(sys.argv[2])
text = src.read_text(encoding="utf-8")
line = "        include /www/server/nginx/conf/voxbulk-api-upstream.conf;\n"
if "voxbulk-api-upstream.conf" in text or "upstream voxbulk_api" in text:
    out.write_text(text, encoding="utf-8")
    print("already present")
    raise SystemExit(0)
for marker in (
    "include /www/server/nginx/conf/voxbulk-api-limits.conf;",
    "include /www/server/nginx/conf/voxbulk-smart-card-limit.conf;",
    "include /www/server/panel/vhost/nginx/*.conf;",
):
    if marker in text:
        text = text.replace(marker, line + marker, 1)
        out.write_text(text, encoding="utf-8")
        print("patched")
        raise SystemExit(0)
raise SystemExit("Could not find insertion point in nginx.conf")
PY
  sudo cp -a "$tmp" "$NGINX_CONF"
  rm -f "$tmp"
  echo "Patched $NGINX_CONF to include upstream"
else
  echo "nginx.conf already references voxbulk_api upstream — skip"
fi

# API B must be listening before nginx starts sending it traffic.
if ! curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8001/health >/dev/null 2>&1 \
  && ! curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8001/health >/dev/null 2>&1; then
  echo "Starting voxbulk-api-b (:8001) before switching nginx …"
  if [[ -f /etc/systemd/system/voxbulk-api-b.service ]]; then
    systemctl start voxbulk-api-b.service || true
  else
    echo "Missing voxbulk-api-b.service — run: sudo bash $ROOT/scripts/vps-setup-api-systemd.sh"
  fi
  ok=0
  for _ in $(seq 1 30); do
    if curl -sf -H "Host: api.voxbulk.com" http://127.0.0.1:8001/health >/dev/null 2>&1 \
      || curl -sf -H "Host: 127.0.0.1" http://127.0.0.1:8001/health >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 1
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "WARN: :8001 not healthy yet — nginx will skip it (max_fails) until it comes up"
  fi
else
  echo "API B already healthy on :8001"
fi

echo "Patching $NGINX_VHOST proxy_pass → voxbulk_api …"
sudo cp -a "$NGINX_VHOST" "${NGINX_VHOST}.bak.dual-api-$(date +%Y%m%d%H%M%S)"
tmp="$(mktemp)"
python3 - "$NGINX_VHOST" "$tmp" <<'PY'
from pathlib import Path
import sys

vhost = Path(sys.argv[1])
out = Path(sys.argv[2])
text = vhost.read_text(encoding="utf-8")
text = text.replace("proxy_pass http://127.0.0.1:8000;", "proxy_pass http://voxbulk_api;")
out_lines = []
raw = text.splitlines()
i = 0
while i < len(raw):
    line = raw[i]
    out_lines.append(line)
    if line.strip() == "proxy_pass http://voxbulk_api;":
        nxt = raw[i + 1].strip() if i + 1 < len(raw) else ""
        if not nxt.startswith("proxy_next_upstream"):
            indent = line[: len(line) - len(line.lstrip())]
            out_lines.append(f"{indent}proxy_next_upstream error timeout http_502 http_503;")
            out_lines.append(f"{indent}proxy_next_upstream_tries 2;")
    i += 1
text = "\n".join(out_lines)
if not text.endswith("\n"):
    text += "\n"
out.write_text(text, encoding="utf-8")
print("patched")
PY
sudo cp -a "$tmp" "$NGINX_VHOST"
rm -f "$tmp"

echo "Testing nginx config…"
nginx -t
nginx -s reload || systemctl reload nginx
echo "OK — api.voxbulk.com load-balances :8000 and :8001"
echo "Smoke: curl -s https://api.voxbulk.com/health"
echo "       curl -s -H 'Host: api.voxbulk.com' http://127.0.0.1:8000/health"
echo "       curl -s -H 'Host: api.voxbulk.com' http://127.0.0.1:8001/health"
