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
echo "Card subscription checks (Stripe / Airwallex — sandbox keys in Admin):"
echo "  5. Packages checkout → subscription active, paid invoice, NOT wallet top-up"
echo "  6. Celery worker + beat running (sudo bash scripts/vps-setup-celery.sh if missing)"
echo "  7. Auto-renewal at period end (or set current_period_end past for test org)"
echo "  8. Failed renewal → payment_failed email + dd_next_retry_at"
echo "  9. Upgrade → pro-rata charge + payment_receipt email"
echo " 10. Downgrade → pending_plan_id + billing_plan_change_scheduled email"
echo " 11. Cancel → billing_cancellation_requested → billing_subscription_ended"
echo ""
echo "Customer Feedback (GCC org, e.g. AE):"
echo " 12. /account/feedback/packages → card checkout (Airwallex) activates feedback sub"
echo ""
echo "Local pytest (before/after deploy):"
echo "  pytest tests/test_card_subscription_checkout.py tests/test_stripe_subscription_renewal.py \\"
echo "    tests/test_airwallex_subscription_renewal.py tests/test_card_renewal_lifecycle.py \\"
echo "    tests/test_card_plan_change.py tests/test_feedback_card_subscription.py -q"
echo ""
echo "Done."
