#!/usr/bin/env bash
# One-time VPS: Content-Security-Policy-Report-Only on static/public nginx vhosts.
# Report-only first — does not block. Review browser/console + POST /csp-report for 7 days.
#   cd /www/voxbulk && git pull origin main && sudo bash scripts/vps-install-csp-report-only.sh
set -euo pipefail

HEADER_FILE="${VOX_CSP_INCLUDE:-/www/server/nginx/conf/voxbulk-csp-report-only.conf}"

sudo tee "$HEADER_FILE" >/dev/null <<'EOF'
# Report-only CSP (Phase 2). Does not enforce. Managed by vps-install-csp-report-only.sh
add_header Content-Security-Policy-Report-Only "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src 'self' https://api.voxbulk.com wss: https: blob:; media-src 'self' blob: mediastream:; worker-src 'self' blob:; frame-src 'self' https://js.stripe.com https://hooks.stripe.com https://www.google.com https://accounts.google.com; report-uri https://api.voxbulk.com/csp-report;" always;
EOF
echo "Wrote $HEADER_FILE"

patch_vhost() {
  local vhost="$1"
  if [[ ! -f "$vhost" ]]; then
    echo "skip missing $vhost"
    return 0
  fi
  if grep -q 'voxbulk-csp-report-only.conf' "$vhost" 2>/dev/null; then
    echo "already included in $vhost"
    return 0
  fi
  sudo cp -a "$vhost" "${vhost}.bak.csp-$(date +%Y%m%d%H%M%S)"
  local tmp
  tmp="$(mktemp)"
  python3 - "$vhost" "$tmp" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
out = Path(sys.argv[2])
text = path.read_text(encoding="utf-8")
line = "    include /www/server/nginx/conf/voxbulk-csp-report-only.conf;\n"
if "voxbulk-csp-report-only.conf" in text:
    out.write_text(text, encoding="utf-8")
    raise SystemExit(0)
marker = "    error_page 497"
if marker in text:
    text = text.replace(marker, line + marker, 1)
else:
    # After first ssl_session_timeout / HSTS block
    marker2 = "    add_header Strict-Transport-Security"
    if marker2 not in text:
        raise SystemExit(f"no insertion point in {path}")
    nl = text.find("\n", text.find(marker2))
    text = text[: nl + 1] + line + text[nl + 1 :]
out.write_text(text, encoding="utf-8")
PY
  sudo cp -a "$tmp" "$vhost"
  rm -f "$tmp"
  echo "patched $vhost"
}

patch_vhost "${VOX_DASH_VHOST:-/www/server/panel/vhost/nginx/dashboard.voxbulk.com.conf}"
patch_vhost "${VOX_ADMIN_VHOST:-/www/server/panel/vhost/nginx/admin.voxbulk.com.conf}"
patch_vhost "${VOX_PUBLIC_VHOST:-/www/server/panel/vhost/nginx/voxbulk.com.conf}"

echo "Testing nginx config…"
sudo nginx -t
sudo nginx -s reload || sudo systemctl reload nginx
echo "OK — CSP Report-Only on dashboard, admin, and public. Watch DevTools + API /csp-report for 7 days before enforcing."
