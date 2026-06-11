#!/usr/bin/env bash
# Finance release smoke checks — run on VPS after deploy.
# Usage: cd /www/voxbulk && bash scripts/vps-finance-smoke.sh
#
# Optional: VOX_RUN_FINANCE_PYTEST=1 to run pytest (dev/CI only — needs test DB fixtures)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$ROOT/voxbulk-api"
PASS=0
FAIL=0
WARN=0

pass() { echo "PASS  $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL  $*"; FAIL=$((FAIL + 1)); }
warn() { echo "WARN  $*"; WARN=$((WARN + 1)); }

if [[ -x "$API_DIR/.venv/bin/python3" ]]; then
  PYTHON="$API_DIR/.venv/bin/python3"
else
  PYTHON="python3"
fi

echo "=== VoxBulk finance smoke ==="
echo "host: $(hostname)"
echo "time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "root: $ROOT"
echo "python: $PYTHON"
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
  if command -v alembic >/dev/null 2>&1 || [[ -x "$API_DIR/.venv/bin/alembic" ]]; then
    ALEMBIC="alembic"
    [[ -x "$API_DIR/.venv/bin/alembic" ]] && ALEMBIC="$API_DIR/.venv/bin/alembic"
    current="$("$ALEMBIC" current 2>/dev/null | tail -n 1 || true)"
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
  curl -s http://127.0.0.1:8000/health/build | "$PYTHON" -m json.tool 2>/dev/null | head -n 20 || true
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

echo "--- DB finance checks (production MySQL) ---"
cd "$API_DIR"
export PYTHONPATH="$API_DIR${PYTHONPATH:+:$PYTHONPATH}"
DB_OUT="$("$PYTHON" - <<'PY'
import sys
from sqlalchemy import func, select

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackPackage
from app.models.plan_price import PlanPrice
from app.models.subscription import Subscription
from app.services.plan_price_service import PlanPriceService

results: list[tuple[str, str]] = []

with get_sessionmaker()() as db:
    PlanPriceService.ensure_seeded(db)
    eur_count = db.execute(
        select(func.count()).select_from(PlanPrice).where(PlanPrice.currency == "EUR")
    ).scalar_one()
    print(f"EUR PlanPrice rows: {eur_count}")
    if int(eur_count or 0) > 0:
        results.append(("pass", "EUR PlanPrice rows exist"))
    else:
        results.append(("fail", "no EUR PlanPrice rows"))

    missing_gc = db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.payment_provider == "gocardless",
            Subscription.external_subscription_id.is_(None),
            Subscription.status.in_(["active", "trial", "past_due", "pending_first_payment"]),
        )
    ).scalar_one()
    print(f"GC subs missing external_subscription_id: {missing_gc}")
    if int(missing_gc or 0) == 0:
        results.append(("pass", "all active GC subs have external_subscription_id"))
    else:
        results.append(("warn", f"{missing_gc} active GC subs missing external_subscription_id"))

    zones = ("gb", "eu", "us", "ca", "au")
    for zone in zones:
        count = db.execute(
            select(func.count()).select_from(FeedbackPackage).where(FeedbackPackage.market_zone == zone)
        ).scalar_one()
        label = "pass" if int(count or 0) >= 3 else "fail"
        results.append((label, f"feedback packages zone={zone}: {count} (expect >= 3)"))

for level, msg in results:
    print(f"RESULT:{level}:{msg}")
PY
)" || fail "python finance checks errored"

while IFS= read -r line; do
  case "$line" in
    RESULT:pass:*) pass "${line#RESULT:pass:}" ;;
    RESULT:fail:*) fail "${line#RESULT:fail:}" ;;
    RESULT:warn:*) warn "${line#RESULT:warn:}" ;;
    *) [[ -n "$line" ]] && echo "$line" ;;
  esac
done <<< "$DB_OUT"
echo ""

echo "--- billing pytest subset ---"
if [[ "${VOX_RUN_FINANCE_PYTEST:-}" == "1" ]]; then
  cd "$API_DIR"
  if "$PYTHON" -m pytest tests/test_billing_currency.py tests/test_billing_lifecycle.py tests/test_customer_feedback.py tests/test_market_zone.py -q --tb=no; then
    pass "billing pytest subset"
  else
    fail "billing pytest subset — run manually for details"
  fi
else
  warn "billing pytest skipped on VPS (production MySQL — set VOX_RUN_FINANCE_PYTEST=1 on dev/CI only)"
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
