"""Phase 4 — failed card renewal retries and payment-failed emails."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.billing_lifecycle_service import DD_MAX_RETRIES
from app.services.card_renewal_lifecycle_service import CardRenewalLifecycleService
from app.services.stripe_billing_service import SUBSCRIPTION_RENEWAL_KIND
from app.services.stripe_payment_service import StripePaymentService
from app.services.stripe_subscription_service import StripeSubscriptionService


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


def _seed_managed_sub(db) -> tuple[Organisation, Plan, Subscription]:
    org = Organisation(name="Card Retry Org", country="gb", billing_currency="GBP", contact_email="bill@test.com")
    db.add(org)
    db.flush()
    plan = Plan(
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
    db.add(plan)
    db.flush()
    sub = Subscription(
        org_id=org.id,
        plan_id=plan.id,
        status="active",
        payment_provider="stripe",
        service_code="voxbulk",
        external_customer_id="cus_test",
        external_subscription_id="pm_test",
        mandate_status="verified",
        billing_interval="monthly",
        current_period_end=datetime.utcnow() - timedelta(hours=1),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(sub)
    db.commit()
    db.refresh(org)
    db.refresh(plan)
    db.refresh(sub)
    return org, plan, sub


@patch("app.services.product_email_triggers.ProductEmailTriggers.notify_payment_failed", return_value=(True, None))
def test_renewal_failure_schedules_retry_and_emails(_email, db):
    org, plan, sub = _seed_managed_sub(db)
    period_key = sub.current_period_end.strftime("%Y%m%d")

    result = CardRenewalLifecycleService.handle_renewal_failure(
        db,
        org=org,
        sub=sub,
        plan=plan,
        provider="stripe",
        period_key=period_key,
        amount_minor=9900,
        currency="GBP",
        payment_reference="pi_fail_1",
        failure_reason="Card declined",
    )

    assert result["dd_retry_count"] == 1
    assert result["dd_next_retry_at"] is not None
    assert result["status"] == "failed"
    _email.assert_called_once()

    invoice = db.get(BillingInvoice, result["invoice_id"])
    assert invoice is not None
    assert invoice.external_invoice_id == f"sub-renewal:{sub.id}:{period_key}"


@patch("app.services.product_email_triggers.ProductEmailTriggers.notify_payment_failed", return_value=(True, None))
def test_renewal_failure_marks_past_due_after_max_retries(_email, db):
    org, plan, sub = _seed_managed_sub(db)
    period_key = sub.current_period_end.strftime("%Y%m%d")
    ext_inv = CardRenewalLifecycleService.renewal_external_id(sub.id, period_key)

    invoice = BillingInvoice(
        org_id=org.id,
        provider="stripe",
        external_invoice_id=ext_inv,
        client_email=org.contact_email or "bill@test.com",
        amount_gbp_pence=9900,
        subtotal_pence=9900,
        currency="GBP",
        status="failed",
        dd_retry_count=DD_MAX_RETRIES,
        kind="subscription",
    )
    db.add(invoice)
    db.commit()

    result = CardRenewalLifecycleService.handle_renewal_failure(
        db,
        org=org,
        sub=sub,
        plan=plan,
        provider="stripe",
        period_key=period_key,
        amount_minor=9900,
        currency="GBP",
        failure_reason="Still declined",
    )

    assert result["status"] == "past_due"
    assert result["dd_next_retry_at"] is None
    db.refresh(sub)
    assert sub.status == "past_due"


@patch("app.services.billing_event_email_service.BillingEventEmailService.issue_payment_invoice", return_value=(None, None, False))
@patch("app.services.product_email_triggers.ProductEmailTriggers.notify_payment_failed", return_value=(True, None))
def test_stripe_process_due_renewal_failure_schedules_retry(_email, _inv_email, db):
    from app.services.stripe_billing_service import StripeBillingError, StripeBillingService

    org, plan, sub = _seed_managed_sub(db)
    period_key = sub.current_period_end.strftime("%Y%m%d")

    with patch.object(StripeBillingService, "charge_renewal", side_effect=StripeBillingError("declined")):
        with patch("app.services.product_email_triggers.ProductEmailTriggers.notify_payment_failed", return_value=(True, None)):
            result = StripeSubscriptionService.process_due_renewal(db, sub=sub, org=org, plan=plan)

    assert result["renewal_failed"] == "1"
    ext_inv = CardRenewalLifecycleService.renewal_external_id(sub.id, period_key)
    invoice = db.execute(
        __import__("sqlalchemy").select(BillingInvoice).where(
            BillingInvoice.external_invoice_id == ext_inv,
            BillingInvoice.provider == "stripe",
        )
    ).scalar_one_or_none()
    assert invoice is not None
    assert invoice.dd_retry_count == 1
    assert invoice.dd_next_retry_at is not None


@patch("app.services.billing_event_email_service.BillingEventEmailService.issue_payment_invoice", return_value=(None, None, False))
@patch("app.services.product_email_triggers.ProductEmailTriggers.notify_payment_failed", return_value=(True, None))
@patch("app.services.stripe_billing_service.StripeBillingService.charge_renewal")
def test_retry_due_renewals_pays_on_success(mock_charge, _email, _inv_email, db):
    org, plan, sub = _seed_managed_sub(db)
    period_key = sub.current_period_end.strftime("%Y%m%d")
    ext_inv = CardRenewalLifecycleService.renewal_external_id(sub.id, period_key)

    invoice = BillingInvoice(
        org_id=org.id,
        provider="stripe",
        external_invoice_id=ext_inv,
        client_email=org.contact_email or "bill@test.com",
        amount_gbp_pence=9900,
        subtotal_pence=9900,
        currency="GBP",
        status="failed",
        dd_retry_count=1,
        dd_next_retry_at=datetime.utcnow() - timedelta(minutes=5),
        kind="subscription",
    )
    db.add(invoice)
    db.commit()

    mock_charge.return_value = {
        "payment_intent_id": "pi_retry_ok",
        "status": "succeeded",
        "intent": {
            "id": "pi_retry_ok",
            "currency": "gbp",
            "amount_received": 9900,
            "metadata": {
                "voxbulk_kind": SUBSCRIPTION_RENEWAL_KIND,
                "voxbulk_subscription_id": sub.id,
                "voxbulk_period_key": period_key,
            },
        },
    }

    stats = CardRenewalLifecycleService.retry_due_renewals(db)
    assert stats["paid"] == 1
    db.refresh(invoice)
    assert invoice.status == "paid"
    assert invoice.dd_retry_count == 0
    assert invoice.dd_next_retry_at is None


@patch("app.services.product_email_triggers.ProductEmailTriggers.notify_payment_failed", return_value=(True, None))
def test_stripe_webhook_payment_failed_renewal(_email, db):
    org, plan, sub = _seed_managed_sub(db)
    period_key = sub.current_period_end.strftime("%Y%m%d")
    event = {
        "type": "payment_intent.payment_failed",
        "data": {
            "object": {
                "id": "pi_wh_fail",
                "currency": "gbp",
                "amount": 9900,
                "metadata": {
                    "voxbulk_org_id": org.id,
                    "voxbulk_kind": SUBSCRIPTION_RENEWAL_KIND,
                    "voxbulk_subscription_id": sub.id,
                    "voxbulk_period_key": period_key,
                },
                "last_payment_error": {"message": "Your card was declined."},
            }
        },
    }
    result = StripePaymentService.handle_webhook_event(db, event)
    assert result.get("renewal_failed") is True
    assert result.get("dd_retry_count") == 1
    _email.assert_called_once()
