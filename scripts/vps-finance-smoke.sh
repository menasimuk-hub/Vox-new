#!/usr/bin/env bash
# Finance release smoke checks — run on VPS after deploy.
# Usage: cd /www/voxbulk && bash scripts/vps-finance-smoke.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
PASS=0
FAIL=0
WARN=0

pass() { echo "PASS  $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL  $*"; FAIL=$((FAIL + 1)); }
warn() { echo "WARN  $*"; WARN=$((WARN + 1)); }

echo "=== VoxBulk finance smoke ==="
echo "host: $(hostname)"
echo "time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "root: $ROOT"
echo ""

echo "--- git ---"
cd "$ROOT"
if git log -1 --oneline >/dev/null 2>&1; then
  pass "git revision: $(git log -1 --oneline)"
else
  fail "git log unavailable"
fi
echo ""

echo "--- migration 0117 ---"
if [[ -d "$API_DIR" ]]; then
  cd "$API_DIR"
  if command -v alembic >/dev/null 2>&1; then
    current="$(alembic current 2>/dev/null | tail -n 1 || true)"
    if echo "$current" | grep -q "0117_billing_finance_foundation"; then
      pass "alembic current includes 0117_billing_finance_foundation"
    else
      fail "alembic current missing 0117 — got: ${current:-empty}"
    fi
  else
    warn "alembic CLI not found — check migration manually"
  fi
else
  fail "API dir missing: $API_DIR"
fi
echo ""

echo "--- API health ---"
if curl -sf http://127.0.0.1:8000/health/build >/dev/null 2>&1; then
  pass "/health/build reachable"
  curl -s http://127.0.0.1:8000/health/build | python3 -m json.tool 2>/dev/null | head -n 20 || true
else
  fail "/health/build not reachable"
fi
echo ""

echo "--- celery worker ---"
if pgrep -af "celery" >/dev/null 2>&1; then
  pass "celery process running"
  pgrep -af "celery" | head -n 3
else
  warn "no celery process found"
fi
echo ""

echo "--- DB finance checks (python) ---"
cd "$API_DIR"
python3 - <<'PY' || fail "python finance checks errored"
import sys
from sqlalchemy import func, select

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackPackage
from app.models.plan_price import PlanPrice
from app.models.subscription import Subscription
from app.services.plan_price_service import PlanPriceService

with get_sessionmaker()() as db:
    PlanPriceService.ensure_seeded(db)
    eur_count = db.execute(
        select(func.count()).select_from(PlanPrice).where(PlanPrice.currency == "EUR")
    ).scalar_one()
    print(f"EUR PlanPrice rows: {eur_count}")
    if int(eur_count or 0) > 0:
        print("PASS  EUR PlanPrice rows exist")
    else:
        print("FAIL  no EUR PlanPrice rows")

    missing_gc = db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.payment_provider == "gocardless",
            Subscription.external_subscription_id.is_(None),
            Subscription.status.in_(["active", "trial", "past_due", "pending_first_payment"]),
        )
    ).scalar_one()
    print(f"GC subs missing external_subscription_id: {missing_gc}")
    if int(missing_gc or 0) == 0:
        print("PASS  all active GC subs have external_subscription_id")
    else:
        print("WARN  active GC subs missing external_subscription_id — run finance_gc_backfill.py")

    zones = ("gb", "eu", "us", "ca", "au")
    for zone in zones:
        count = db.execute(
            select(func.count()).select_from(FeedbackPackage).where(FeedbackPackage.market_zone == zone)
        ).scalar_one()
        label = "PASS" if int(count or 0) >= 3 else "FAIL"
        print(f"{label}  feedback packages zone={zone}: {count} (expect >= 3)")
PY
echo ""

echo "--- billing pytest subset ---"
cd "$API_DIR"
if python3 -m pytest tests/test_billing_currency.py tests/test_billing_lifecycle.py tests/test_customer_feedback.py tests/test_market_zone.py -q --tb=no 2>/dev/null; then
  pass "billing pytest subset"
else
  fail "billing pytest subset — run manually for details"
fi
echo ""

echo "=== SUMMARY ==="
echo "PASS=$PASS FAIL=$FAIL WARN=$WARN"
if [[ "$FAIL" -gt 0 ]]; then
  echo "OVERALL: FAIL"
  exit 1
fi
echo "OVERALL: PASS (review WARN lines)"
exit 0
