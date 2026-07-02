#!/usr/bin/env bash
# Post-deploy billing smoke checks — run on the Linux VPS after ./deploy-vps.sh
set -euo pipefail

API="${VOX_API_BASE:-http://127.0.0.1:8000}"
echo "== VoxBulk billing deploy verification =="
echo "API base: $API"

check() {
  local path="$1"
  local label="$2"
  echo -n "  $label ... "
  code=$(curl -sS -o /tmp/vox_health.json -w "%{http_code}" "$API$path" || true)
  if [[ "$code" == "200" ]]; then
    echo "OK ($code)"
  else
    echo "FAIL ($code)"
    cat /tmp/vox_health.json 2>/dev/null || true
    exit 1
  fi
}

check "/health" "Health"
check "/health/db" "Database"
check "/health/pricing" "Pricing"

echo ""
echo "Alembic head (expect 0147_billing_value_pool or newer):"
cd "$(dirname "$0")/.."/voxbulk-api
alembic current 2>/dev/null | tail -1 || echo "  (run from voxbulk-api with venv active)"

echo ""
echo "Manual checks (dashboard + admin):"
echo "  1. Usage page — Cost vs Amount due columns; running campaign refreshes."
echo "  2. Complete one AI campaign — single completion invoice (not split period overage)."
echo "  3. Billing page — Core used-only KPIs; Feedback allowance unchanged."
echo "  4. org_usage_periods has allowance_value_included_minor / allowance_value_used_minor."
echo ""
echo "Done."
