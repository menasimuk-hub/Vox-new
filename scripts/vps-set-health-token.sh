#!/usr/bin/env bash
# Set HEALTH_SECRET_TOKEN in voxbulk-api/.env if empty, then reload/restart the API.
# Run on the dedicated server (prints the token once — store it in your uptime monitor):
#   cd /www/voxbulk && bash scripts/vps-set-health-token.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${VOX_ENV_FILE:-$ROOT/voxbulk-api/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

current="$(grep -E '^HEALTH_SECRET_TOKEN=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '\r' | sed 's/^["'\'']//;s/["'\'']$//' || true)"

if [[ -n "$current" && "$current" != "change-me" ]]; then
  echo "HEALTH_SECRET_TOKEN already set (${#current} chars) — not rotating."
  echo "Test: curl -s -o /dev/null -w '%{http_code}\\n' https://api.voxbulk.com/health/build"
  echo "  (expect 403 without header; 200 with X-Health-Token)"
  exit 0
fi

token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

if grep -qE '^HEALTH_SECRET_TOKEN=' "$ENV_FILE"; then
  sed -i "s|^HEALTH_SECRET_TOKEN=.*|HEALTH_SECRET_TOKEN=${token}|" "$ENV_FILE"
else
  printf '\nHEALTH_SECRET_TOKEN=%s\n' "$token" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE" 2>/dev/null || true

echo "Wrote HEALTH_SECRET_TOKEN to $ENV_FILE (${#token} chars)."
echo "Gunicorn does not pick up new .env on HUP — one API restart is required:"
echo "  cd $ROOT && VOX_FORCE_API_RESTART=1 VOX_SKIP_PUBLIC_RESTART=1 ./vox.sh restart"
echo ""
echo "Then:"
echo "  curl -s -o /dev/null -w '%{http_code}\\n' https://api.voxbulk.com/health/build"
echo "  curl -s -H \"X-Health-Token: ${token}\" https://api.voxbulk.com/health/build"
echo ""
echo "Save the token in your uptime monitor. Do not commit .env."
