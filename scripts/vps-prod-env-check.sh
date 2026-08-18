#!/usr/bin/env bash
# Phase 0 — production .env checklist (does not print secret values).
#   cd /www/voxbulk && bash scripts/vps-prod-env-check.sh
set -euo pipefail

ENV_FILE="${VOX_ENV_FILE:-$(cd "$(dirname "$0")/.." && pwd)/voxbulk-api/.env}"
fail=0
warn=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [[ ! -f "$ENV_FILE" ]]; then
  echo -e "${RED}[fail]${NC} missing $ENV_FILE"
  exit 1
fi

mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%OLp' "$ENV_FILE" 2>/dev/null || echo '?')"
if [[ "$mode" != "600" && "$mode" != "400" ]]; then
  echo -e "${YELLOW}[warn]${NC} $ENV_FILE mode is $mode (prefer 600)"
  warn=$((warn + 1))
else
  echo -e "${GREEN}[ok]${NC} $ENV_FILE mode $mode"
fi

get_val() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '\r' | sed 's/^["'\'']//;s/["'\'']$//' || true
}

check_eq() {
  local key="$1" expect="$2"
  local val
  val="$(get_val "$key")"
  if [[ "$val" == "$expect" ]]; then
    echo -e "${GREEN}[ok]${NC} $key=$expect"
  else
    echo -e "${RED}[fail]${NC} $key should be $expect (got '${val:-<unset>}')"
    fail=$((fail + 1))
  fi
}

check_set_not_placeholder() {
  local key="$1"
  local val
  val="$(get_val "$key")"
  if [[ -z "$val" ]]; then
    echo -e "${RED}[fail]${NC} $key is empty"
    fail=$((fail + 1))
    return
  fi
  local lower
  lower="$(echo "$val" | tr '[:upper:]' '[:lower:]')"
  if [[ "$lower" == "change-me" || "$lower" == "changeme" || "$val" == "change-me-local" ]]; then
    echo -e "${RED}[fail]${NC} $key is still a placeholder"
    fail=$((fail + 1))
    return
  fi
  echo -e "${GREEN}[ok]${NC} $key is set (${#val} chars)"
}

echo "=== production env checklist ==="
echo "file: $ENV_FILE"
echo ""

env_name="$(get_val ENV)"
if [[ "$env_name" == "production" || "$env_name" == "prod" ]]; then
  echo -e "${GREEN}[ok]${NC} ENV=$env_name"
else
  echo -e "${RED}[fail]${NC} ENV should be production (got '${env_name:-<unset>}')"
  fail=$((fail + 1))
fi

insecure="$(get_val ALLOW_INSECURE_WEBHOOKS)"
insecure_l="$(echo "${insecure:-0}" | tr '[:upper:]' '[:lower:]')"
if [[ -z "$insecure" || "$insecure_l" == "0" || "$insecure_l" == "false" || "$insecure_l" == "no" ]]; then
  echo -e "${GREEN}[ok]${NC} ALLOW_INSECURE_WEBHOOKS is off"
else
  echo -e "${RED}[fail]${NC} ALLOW_INSECURE_WEBHOOKS must be 0 on production"
  fail=$((fail + 1))
fi

check_eq PUBLIC_APP_ORIGIN "https://voxbulk.com"
check_eq DASHBOARD_APP_ORIGIN "https://dashboard.voxbulk.com"
check_set_not_placeholder JWT_SECRET_KEY
check_set_not_placeholder ENCRYPTION_KEY
check_set_not_placeholder HEALTH_SECRET_TOKEN

sentry_dsn="$(get_val SENTRY_DSN)"
if [[ -n "$sentry_dsn" ]]; then
  echo -e "${GREEN}[ok]${NC} SENTRY_DSN is set (${#sentry_dsn} chars)"
else
  echo -e "${YELLOW}[warn]${NC} SENTRY_DSN is empty — API/Celery errors will not go to Sentry (optional)"
  warn=$((warn + 1))
fi

db="$(get_val DATABASE_URL)"
case "$db" in
  *mysql*|*MySQL*|*pymysql*)
    echo -e "${GREEN}[ok]${NC} DATABASE_URL looks like MySQL"
    ;;
  *)
    echo -e "${YELLOW}[warn]${NC} DATABASE_URL does not look like MySQL"
    warn=$((warn + 1))
    ;;
esac

echo ""
echo "Set HEALTH_SECRET_TOKEN then curl:"
echo "  curl -s -H \"X-Health-Token: <token>\" https://api.voxbulk.com/health/build"
echo ""
if [[ "$fail" -gt 0 ]]; then
  echo -e "${RED}FAILED${NC} $fail required check(s), $warn warning(s)"
  exit 1
fi
echo -e "${GREEN}OK${NC} required checks passed ($warn warning(s))"
exit 0
