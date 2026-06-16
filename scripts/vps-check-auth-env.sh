#!/usr/bin/env bash
# Verify production URL env vars — OAuth redirects to PUBLIC_APP_ORIGIN/signin#access_token=...
# Run on VPS: bash scripts/vps-check-auth-env.sh
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/voxbulk-api/.env"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok() { echo -e "${GREEN}[ok]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*" >&2; }
fail() { echo -e "${RED}[fail]${NC} $*" >&2; }

echo "=== VoxBulk auth / URL env check ==="
echo "File: $ENV_FILE"

if [[ ! -f "$ENV_FILE" ]]; then
  fail "Missing $ENV_FILE"
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE" 2>/dev/null || true

ENV_VAL="${ENV:-development}"
PUBLIC="${PUBLIC_APP_ORIGIN:-}"
DASH="${DASHBOARD_APP_ORIGIN:-}"
CORS="${CORS_ALLOW_ORIGINS:-}"
TRUSTED="${TRUSTED_HOSTS:-}"

echo "ENV=$ENV_VAL"
echo "PUBLIC_APP_ORIGIN=${PUBLIC:-(not set)}"
echo "DASHBOARD_APP_ORIGIN=${DASH:-(not set)}"
echo "CORS_ALLOW_ORIGINS=${CORS:-(not set)}"
echo "TRUSTED_HOSTS=${TRUSTED:-(not set)}"

ISSUES=0

if [[ "$ENV_VAL" != "production" && "$ENV_VAL" != "prod" ]]; then
  warn "ENV is not production — OAuth may still redirect to localhost defaults"
  ISSUES=$((ISSUES + 1))
fi

if [[ -z "$PUBLIC" || "$PUBLIC" == *"localhost"* || "$PUBLIC" == *"127.0.0.1"* ]]; then
  fail "PUBLIC_APP_ORIGIN must be https://voxbulk.com on VPS (OAuth lands here after Google/Apple login)"
  echo "  Add: PUBLIC_APP_ORIGIN=https://voxbulk.com"
  ISSUES=$((ISSUES + 1))
else
  ok "PUBLIC_APP_ORIGIN looks like production"
fi

if [[ -z "$DASH" || "$DASH" == *"localhost"* || "$DASH" == *"127.0.0.1"* ]]; then
  fail "DASHBOARD_APP_ORIGIN should be https://dashboard.voxbulk.com"
  echo "  Add: DASHBOARD_APP_ORIGIN=https://dashboard.voxbulk.com"
  ISSUES=$((ISSUES + 1))
else
  ok "DASHBOARD_APP_ORIGIN looks like production"
fi

if [[ -z "$CORS" ]]; then
  warn "CORS_ALLOW_ORIGINS unset — production fallback may apply; set explicitly for clarity"
else
  ok "CORS_ALLOW_ORIGINS is set"
fi

echo ""
if [[ "$ISSUES" -gt 0 ]]; then
  echo "=== Fix (append to $ENV_FILE then restart) ==="
  cat <<'EOF'
ENV=production
PUBLIC_APP_ORIGIN=https://voxbulk.com
DASHBOARD_APP_ORIGIN=https://dashboard.voxbulk.com
CORS_ALLOW_ORIGINS=https://voxbulk.com,https://www.voxbulk.com,https://admin.voxbulk.com,https://dashboard.voxbulk.com
TRUSTED_HOSTS=api.voxbulk.com,localhost,127.0.0.1
EOF
  echo ""
  echo "Then: cd /www/voxbulk && ./vox.sh restart"
  exit 1
fi

ok "Auth URL env looks correct. OAuth should redirect to ${PUBLIC}/signin#access_token=..."
exit 0
