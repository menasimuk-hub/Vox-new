"""Smart Card seat upgrades charge prorated; interval change helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.models.subscription import Subscription
from app.services.smart_card.billing_service import SmartCardBillingService


def test_calculate_seat_add_charge_half_period():
    # 1 seat × 4800 yearly × 0.5 remaining = 2400
    assert (
        SmartCardBillingService.calculate_seat_add_charge_minor(
            unit_minor=4800,
            seats_added=1,
            remaining_fraction=0.5,
        )
        == 2400
    )


def test_calculate_seat_add_charge_zero_when_no_add():
    assert (
        SmartCardBillingService.calculate_seat_add_charge_minor(
            unit_minor=4800,
            seats_added=0,
            remaining_fraction=1.0,
        )
        == 0
    )


def test_period_remaining_fraction_mid_month():
    now = datetime.utcnow()
    sub = Subscription(
        id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        plan_id=str(uuid.uuid4()),
        service_code="smart_card",
        status="active",
        billing_interval="monthly",
        current_period_end=now + timedelta(days=15),
    )
    frac = SmartCardBillingService.period_remaining_fraction(sub)
    assert 0.3 < frac < 0.7


def test_update_seats_upgrade_charges_and_billable():
    from app.models.organisation import Organisation
    from app.models.plan import Plan

    org_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    org = Organisation(id=org_id, name="Org", billing_currency="GBP")
    plan = Plan(id=plan_id, code="sc", name="SC", service_kind="smart_card")
    now = datetime.utcnow()
    sub = Subscription(
        id=str(uuid.uuid4()),
        org_id=org_id,
        plan_id=plan_id,
        service_code="smart_card",
        status="active",
        payment_provider="stripe",
        external_customer_id="cus_x",
        external_subscription_id="pm_x",
        seat_quantity=2,
        billable_seat_quantity=2,
        billing_interval="yearly",
        billing_currency="GBP",
        current_period_end=now + timedelta(days=180),
        amount_next_payment_minor=9600,
    )
    db = MagicMock()

    def _get(model, key):
        if key == org_id:
            return org
        if key == plan_id:
            return plan
        return None

    db.get.side_effect = _get

    with (
        patch(
            "app.services.billing_access_service.BillingAccessService.get_subscription",
            return_value=sub,
        ),
        patch(
            "app.services.smart_card.company_service.SmartCardEntitlementService.active_rep_count",
            return_value=2,
        ),
        patch.object(SmartCardBillingService, "promote_free_seats_if_due", return_value=False),
        patch.object(
            SmartCardBillingService,
            "period_remaining_fraction",
            return_value=0.5,
        ),
        patch(
            "app.services.plan_price_service.PlanPriceService.billing_amount_for_org",
            return_value=("GBP", 4800, "yearly"),
        ),
        patch(
            "app.services.plan_price_service.PlanPriceService.subscription_charge_amount_for_org",
            return_value=("GBP", 14400),
        ),
        patch.object(
            SmartCardBillingService,
            "_charge_adjustment",
            return_value={"charged_minor": 2400, "invoice_id": "inv1", "provider": "stripe"},
        ) as charge,
        patch.object(SmartCardBillingService, "sync_gocardless_billable_amount", return_value=False),
        patch(
            "app.services.billing_finance_service.BillingFinanceService.sync_subscription_billing_fields",
        ),
        patch.object(
            SmartCardBillingService,
            "seats_payload",
            return_value={"seat_quantity": 3, "charge_now_minor": 2400},
        ),
    ):
        result = SmartCardBillingService.update_seats(db, org_id=org_id, seat_quantity=3)

    assert sub.seat_quantity == 3
    assert sub.billable_seat_quantity == 3
    assert sub.added_seats_free_until is None
    charge.assert_called_once()
    assert charge.call_args.kwargs["amount_minor"] == 2400
    assert result["seat_quantity"] == 3


def test_update_seats_downgrade_blocked_by_active_reps():
    from app.models.organisation import Organisation
    from app.models.plan import Plan
    from app.services.smart_card.billing_service import SmartCardBillingError
    import pytest

    org_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    org = Organisation(id=org_id, name="Org")
    plan = Plan(id=plan_id, code="sc", name="SC", service_kind="smart_card")
    sub = Subscription(
        id=str(uuid.uuid4()),
        org_id=org_id,
        plan_id=plan_id,
        service_code="smart_card",
        status="active",
        seat_quantity=2,
        billable_seat_quantity=2,
        billing_interval="monthly",
    )
    db = MagicMock()
    db.get.side_effect = lambda model, key: org if key == org_id else (plan if key == plan_id else None)

    with (
        patch(
            "app.services.billing_access_service.BillingAccessService.get_subscription",
            return_value=sub,
        ),
        patch(
            "app.services.smart_card.company_service.SmartCardEntitlementService.active_rep_count",
            return_value=2,
        ),
        patch.object(SmartCardBillingService, "promote_free_seats_if_due", return_value=False),
        pytest.raises(SmartCardBillingError) as exc,
    ):
        SmartCardBillingService.update_seats(db, org_id=org_id, seat_quantity=1)

    assert "active representative" in str(exc.value).lower()
