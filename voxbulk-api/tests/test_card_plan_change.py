"""Phase 5 — card plan change and cancel credential cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_lifecycle_service import BillingLifecycleService
from app.services.card_plan_change_service import CardPlanChangeService, PRO_RATA_UPGRADE_KIND
from app.services.subscription_cancellation_service import (
    CANCELLATION_SCHEDULED,
    SubscriptionCancellationService,
)


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_plans(db) -> tuple[Organisation, Plan, Plan, Subscription]:
    org = Organisation(name="Plan Change Org", country="gb", billing_currency="GBP", contact_email="bill@test.com")
    db.add(org)
    db.flush()
    starter = Plan(
        code="starter",
        name="Starter",
        price_gbp_pence=9900,
        interval="month",
        calls_included=500,
        whatsapp_included=200,
        overage_per_min_pence=35,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    growth = Plan(
        code="growth",
        name="Growth",
        price_gbp_pence=19900,
        interval="month",
        calls_included=1500,
        whatsapp_included=500,
        overage_per_min_pence=30,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(starter)
    db.add(growth)
    db.flush()
    sub = Subscription(
        org_id=org.id,
        plan_id=starter.id,
        status="active",
        payment_provider="stripe",
        service_code="voxbulk",
        external_customer_id="cus_test",
        external_subscription_id="pm_test",
        mandate_status="verified",
        billing_interval="monthly",
        current_period_end=datetime.utcnow() + timedelta(days=15),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(sub)
    db.commit()
    db.refresh(org)
    db.refresh(starter)
    db.refresh(growth)
    db.refresh(sub)
    return org, starter, growth, sub


def test_card_downgrade_schedules_pending_plan(db):
    org, starter, growth, sub = _seed_plans(db)
    with patch(
        "app.services.billing_refund_email_service.BillingRefundEmailService.send_plan_change_scheduled"
    ) as mock_email:
        result = CardPlanChangeService.apply_downgrade(db, sub=sub, new_plan=growth, billing_interval="monthly")
    assert result["pending_plan_id"] == growth.id
    db.refresh(sub)
    assert sub.pending_plan_id == growth.id
    assert sub.plan_id == starter.id
    mock_email.assert_called_once()
    kwargs = mock_email.call_args.kwargs
    assert kwargs["current_plan_name"] == "Starter"
    assert kwargs["pending_plan_name"] == "Growth"
    assert kwargs["org"].id == org.id


@patch("app.services.billing_refund_email_service.BillingRefundEmailService.send_plan_change_scheduled")
def test_change_subscription_plan_gc_downgrade_sends_email(mock_email, db):
    org, starter, growth, sub = _seed_plans(db)
    sub.payment_provider = "gocardless"
    sub.plan_id = growth.id
    sub.external_customer_id = "CU123"
    sub.mandate_id = "MD123"
    db.add(sub)
    db.commit()

    sub_out, plan_out, direction, extra = BillingLifecycleService.change_subscription_plan(
        db, org_id=org.id, plan_id=starter.id, billing_interval="monthly"
    )

    assert direction == "downgrade"
    assert plan_out.id == starter.id
    assert sub_out.pending_plan_id == starter.id
    mock_email.assert_called_once()


@patch("app.services.billing_event_email_service.BillingEventEmailService.send_payment_receipt", return_value=(True, None))
@patch("app.services.stripe_billing_service.StripeBillingService.charge_managed_payment")
def test_card_upgrade_charges_pro_rata_and_updates_plan(mock_charge, _receipt, db):
    org, starter, growth, sub = _seed_plans(db)
    mock_charge.return_value = {"payment_intent_id": "pi_upgrade", "status": "succeeded", "intent": {}}

    result = CardPlanChangeService.apply_upgrade_with_pro_rata(
        db, org_id=org.id, sub=sub, old_plan=starter, new_plan=growth
    )

    assert result["plan_id"] == growth.id
    assert result["pro_rata_minor"] > 0
    db.refresh(sub)
    assert sub.plan_id == growth.id
    mock_charge.assert_called_once()


@patch("app.services.product_email_triggers.ProductEmailTriggers.notify_payment_failed", return_value=(True, None))
@patch("app.services.stripe_billing_service.StripeBillingService.charge_managed_payment")
def test_card_upgrade_failure_keeps_plan(mock_charge, _email, db):
    org, starter, growth, sub = _seed_plans(db)
    mock_charge.return_value = {"payment_intent_id": "pi_fail", "status": "failed", "intent": {}}

    with pytest.raises(Exception):
        CardPlanChangeService.apply_upgrade_with_pro_rata(
            db, org_id=org.id, sub=sub, old_plan=starter, new_plan=growth
        )

    db.refresh(sub)
    assert sub.plan_id == starter.id
    _email.assert_called_once()


@patch("app.services.billing_event_email_service.BillingEventEmailService.send_payment_receipt", return_value=(True, None))
@patch("app.services.stripe_billing_service.StripeBillingService.charge_managed_payment")
def test_change_subscription_plan_routes_stripe_upgrade(mock_charge, _receipt, db):
    org, starter, growth, sub = _seed_plans(db)
    mock_charge.return_value = {"payment_intent_id": "pi_up", "status": "succeeded", "intent": {}}

    sub_out, plan_out, direction, extra = BillingLifecycleService.change_subscription_plan(
        db, org_id=org.id, plan_id=growth.id, billing_interval="monthly"
    )

    assert direction == "upgrade"
    assert plan_out.id == growth.id
    assert sub_out.plan_id == growth.id
    assert extra is not None
    assert extra.get("pro_rata_minor", 0) >= 0


def test_finalize_cancellation_clears_card_credentials(db):
    org, starter, _growth, sub = _seed_plans(db)
    sub.cancellation_status = CANCELLATION_SCHEDULED
    sub.cancellation_effective_at = datetime.utcnow() - timedelta(minutes=1)
    sub.cancel_at_period_end = True
    db.add(sub)
    db.commit()

    with patch.object(
        SubscriptionCancellationService,
        "_notify_subscription_ended",
    ):
        stats = SubscriptionCancellationService.finalize_due_scheduled_cancellations(db)

    assert stats["finalized"] == 1
    db.refresh(sub)
    assert sub.external_customer_id is None
    assert sub.external_subscription_id is None
    assert sub.status == "cancelled"
