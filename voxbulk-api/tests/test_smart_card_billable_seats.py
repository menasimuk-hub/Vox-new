"""Smart Card option A — new seats free 30 days; billable vs entitled."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.models.subscription import Subscription
from app.services.smart_card.billing_service import (
    DEFAULT_SMART_CARD_TRIAL_DAYS,
    SmartCardBillingService,
)


def test_promote_free_seats_when_window_elapsed():
    sub = Subscription(
        id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        plan_id=str(uuid.uuid4()),
        service_code="smart_card",
        status="active",
        seat_quantity=3,
        billable_seat_quantity=2,
        added_seats_free_until=datetime.utcnow() - timedelta(hours=1),
    )
    db = MagicMock()
    changed = SmartCardBillingService.promote_free_seats_if_due(db, sub, commit=False)
    assert changed is True
    assert sub.billable_seat_quantity == 3
    assert sub.added_seats_free_until is None


def test_promote_free_seats_noop_while_window_open():
    sub = Subscription(
        id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        plan_id=str(uuid.uuid4()),
        service_code="smart_card",
        status="active",
        seat_quantity=3,
        billable_seat_quantity=2,
        added_seats_free_until=datetime.utcnow() + timedelta(days=10),
    )
    db = MagicMock()
    changed = SmartCardBillingService.promote_free_seats_if_due(db, sub, commit=False)
    assert changed is False
    assert sub.billable_seat_quantity == 2


def test_effective_billable_zero_during_trial():
    sub = Subscription(
        id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        plan_id=str(uuid.uuid4()),
        service_code="smart_card",
        status="trial",
        seat_quantity=5,
        billable_seat_quantity=0,
    )
    assert SmartCardBillingService.effective_billable_seats(sub) == 0


def test_default_trial_days_constant():
    assert DEFAULT_SMART_CARD_TRIAL_DAYS == 30


def test_plan_price_uses_billable_seats():
    from app.models.organisation import Organisation
    from app.models.plan import Plan
    from app.services.plan_price_service import PlanPriceService

    org = Organisation(id=str(uuid.uuid4()), name="Org")
    plan = Plan(id=str(uuid.uuid4()), code="sc", name="SC", service_kind="smart_card")
    sub = Subscription(
        id=str(uuid.uuid4()),
        org_id=org.id,
        plan_id=plan.id,
        service_code="smart_card",
        status="active",
        seat_quantity=5,
        billable_seat_quantity=2,
        billing_interval="monthly",
    )
    db = MagicMock()
    with patch.object(
        PlanPriceService,
        "billing_amount_for_org",
        return_value=("GBP", 500, "monthly"),
    ):
        currency, amount = PlanPriceService.subscription_charge_amount_for_org(db, org, plan, sub)
    assert currency == "GBP"
    assert amount == 1000  # 2 billable × 500
