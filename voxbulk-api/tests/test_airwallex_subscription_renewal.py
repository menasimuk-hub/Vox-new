"""Airwallex MIT subscription renewals (Phase 2)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.services.airwallex_billing_service import AirwallexBillingService, SUBSCRIPTION_RENEWAL_KIND
from app.services.airwallex_payment_service import AirwallexPaymentService
from app.services.airwallex_subscription_service import AirwallexSubscriptionService
from app.services.billing_lifecycle_service import BillingLifecycleService


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
    org = Organisation(name="AWX Renew Org", country="gb", billing_currency="GBP", contact_email="bill@test.com")
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
        payment_provider="airwallex",
        service_code="voxbulk",
        external_customer_id="cus_test",
        mandate_id="pct_test",
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


def test_is_managed_subscription():
    sub = Subscription(
        payment_provider="airwallex",
        external_customer_id="cus",
        mandate_id="pct",
        external_subscription_id="pm",
    )
    assert AirwallexBillingService.is_managed_subscription(sub) is True
    sub.mandate_id = None
    assert AirwallexBillingService.is_managed_subscription(sub) is False


def test_parse_intent_credentials():
    intent = {
        "customer_id": "cus_1",
        "payment_consent_id": "pct_1",
        "latest_payment_attempt": {"payment_method": {"id": "pm_1"}},
    }
    creds = AirwallexBillingService.parse_intent_credentials(intent)
    assert creds["customer_id"] == "cus_1"
    assert creds["payment_consent_id"] == "pct_1"
    assert creds["payment_method_id"] == "pm_1"


@patch.object(AirwallexPaymentService, "retrieve_intent")
def test_sync_credentials_from_intent(mock_retrieve, db):
    org, plan, sub = _seed_managed_sub(db)
    sub.external_customer_id = None
    sub.mandate_id = None
    sub.external_subscription_id = None
    db.add(sub)
    db.commit()
    mock_retrieve.return_value = {
        "id": "int_checkout",
        "customer_id": "cus_new",
        "payment_consent_id": "pct_new",
        "latest_payment_attempt": {"payment_method": {"id": "pm_new"}},
        "payment_consent_status": "VERIFIED",
    }
    updated = AirwallexBillingService.sync_credentials_from_intent(db, sub, payment_intent_id="int_checkout")
    assert updated.external_customer_id == "cus_new"
    assert updated.mandate_id == "pct_new"
    assert updated.external_subscription_id == "pm_new"


@patch("app.services.billing_event_email_service.BillingEventEmailService.issue_payment_invoice", return_value=(None, None, False))
@patch.object(AirwallexBillingService, "charge_renewal")
def test_process_due_renewal_charges_and_advances(mock_charge, _email, db):
    org, plan, sub = _seed_managed_sub(db)
    mock_charge.return_value = {
        "payment_intent_id": "int_renew",
        "status": "SUCCEEDED",
        "intent": {
            "id": "int_renew",
            "currency": "USD",
            "captured_amount": 99.0,
            "metadata": {
                "voxbulk_kind": SUBSCRIPTION_RENEWAL_KIND,
                "voxbulk_subscription_id": sub.id,
                "voxbulk_period_key": sub.current_period_end.strftime("%Y%m%d"),
            },
        },
    }
    old_end = sub.current_period_end
    result = AirwallexSubscriptionService.process_due_renewal(db, sub=sub, org=org, plan=plan)
    assert result["renewal_charged"] == "1"
    db.refresh(sub)
    assert sub.current_period_end > old_end


@patch.object(AirwallexSubscriptionService, "process_due_renewal")
@patch("app.services.billing_lifecycle_service.BillingLifecycleService._gocardless_managed_subscription", return_value=False)
def test_lifecycle_routes_airwallex_managed(_gc, mock_renewal, db):
    org, plan, sub = _seed_managed_sub(db)
    mock_renewal.return_value = {"renewal_charged": "1"}
    stats = BillingLifecycleService.process_due_monthly_billing(db)
    assert stats["checked"] >= 1
    mock_renewal.assert_called_once()


@patch("app.services.billing_event_email_service.BillingEventEmailService.issue_payment_invoice", return_value=(None, None, False))
def test_webhook_subscription_renewal(_email, db):
    org, plan, sub = _seed_managed_sub(db)
    period_key = sub.current_period_end.strftime("%Y%m%d")
    event = {
        "name": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "int_wh_renew",
                "currency": "USD",
                "captured_amount": 99.0,
                "metadata": {
                    "voxbulk_org_id": org.id,
                    "voxbulk_kind": SUBSCRIPTION_RENEWAL_KIND,
                    "voxbulk_subscription_id": sub.id,
                    "voxbulk_period_key": period_key,
                },
            }
        },
    }
    old_end = sub.current_period_end
    result = AirwallexPaymentService.handle_webhook_event(db, event)
    assert result.get("renewal_paid") is True
    db.refresh(sub)
    assert sub.current_period_end > old_end
