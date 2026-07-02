"""Phase 1: card subscription checkout uses subscription_checkout metadata, not wallet top-up."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.wallet_transaction import WalletTransaction
from app.services.airwallex_payment_service import AirwallexPaymentService
from app.services.airwallex_billing_service import AirwallexBillingService
from app.services.card_subscription_activation_service import (
    SUBSCRIPTION_CHECKOUT_KIND,
    CardSubscriptionActivationService,
)
from app.services.stripe_payment_service import StripePaymentService
from app.services.stripe_billing_service import StripeBillingService


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


def _seed_plan(db) -> tuple[Organisation, Plan]:
    org = Organisation(name="Card Sub Org", country="gb", billing_currency="GBP")
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
    db.commit()
    db.refresh(org)
    db.refresh(plan)
    return org, plan


@patch.object(StripeBillingService, "ensure_customer", return_value="cus_test")
@patch.object(StripePaymentService, "get_config", return_value={"enabled": True, "publishable_key": "pk_test", "secret_key": "sk_test"})
@patch.object(StripePaymentService, "_request")
def test_stripe_subscription_checkout_intent_metadata(mock_request, _cfg, _customer, db):
    org, plan = _seed_plan(db)
    mock_request.return_value = {
        "id": "pi_sub_test",
        "client_secret": "sec",
        "amount": 9900,
        "status": "requires_payment_method",
    }
    StripePaymentService.create_subscription_checkout_intent(
        db,
        org,
        amount_minor=9900,
        plan_id=plan.id,
        billing_interval="monthly",
    )
    call_data = mock_request.call_args.kwargs["data"]
    assert call_data["metadata[voxbulk_kind]"] == SUBSCRIPTION_CHECKOUT_KIND
    assert call_data["metadata[voxbulk_plan_id]"] == plan.id
    assert call_data["metadata[voxbulk_org_id]"] == org.id
    assert call_data.get("customer") == "cus_test"
    assert call_data.get("setup_future_usage") == "off_session"


@patch.object(AirwallexBillingService, "ensure_customer", return_value="cus_test")
@patch.object(AirwallexPaymentService, "get_config", return_value={"enabled": True, "environment": "demo"})
@patch.object(AirwallexPaymentService, "_request")
def test_airwallex_subscription_checkout_intent_metadata(mock_request, _cfg, _customer, db):
    org, plan = _seed_plan(db)
    mock_request.return_value = {
        "id": "int_sub_test",
        "client_secret": "sec",
        "status": "REQUIRES_PAYMENT_METHOD",
    }
    AirwallexPaymentService.create_subscription_checkout_intent(
        db,
        org,
        amount_minor=9900,
        plan_id=plan.id,
        billing_interval="monthly",
    )
    payload = mock_request.call_args[1]["payload"]
    assert payload["metadata"]["voxbulk_kind"] == SUBSCRIPTION_CHECKOUT_KIND
    assert payload["metadata"]["voxbulk_plan_id"] == plan.id
    assert payload.get("customer_id") == "cus_test"
    assert payload.get("payment_consent", {}).get("merchant_trigger_reason") == "scheduled"


def test_activate_from_payment_creates_sub_and_invoice(db):
    org, plan = _seed_plan(db)
    org.contact_email = "billing@card-sub.test"
    db.add(org)
    db.commit()

    sub = CardSubscriptionActivationService.activate_from_payment(
        db,
        org=org,
        plan=plan,
        provider="airwallex",
        payment_intent_id="pi_activate_1",
        billing_interval="monthly",
    )
    assert sub.status == "active"
    assert sub.payment_provider == "airwallex"
    assert sub.external_subscription_id == "pi_activate_1"
    assert sub.current_period_end is not None
    assert sub.first_payment_at is not None

    ext = CardSubscriptionActivationService.external_invoice_id("airwallex", "pi_activate_1")
    invoice = db.query(BillingInvoice).filter(BillingInvoice.external_invoice_id == ext).one()
    assert invoice.status == "paid"
    assert invoice.kind == "subscription"


def test_activate_from_payment_idempotent(db):
    org, plan = _seed_plan(db)
    org.contact_email = "billing@card-sub.test"
    db.add(org)
    db.commit()

    sub1 = CardSubscriptionActivationService.activate_from_payment(
        db, org=org, plan=plan, provider="stripe", payment_intent_id="pi_dup", billing_interval="monthly"
    )
    sub2 = CardSubscriptionActivationService.activate_from_payment(
        db, org=org, plan=plan, provider="stripe", payment_intent_id="pi_dup", billing_interval="monthly"
    )
    assert sub1.id == sub2.id
    count = db.query(BillingInvoice).count()
    assert count == 1


def test_activate_upserts_existing_subscription(db):
    org, plan = _seed_plan(db)
    org.contact_email = "billing@card-sub.test"
    existing = Subscription(
        org_id=org.id,
        plan_id=plan.id,
        status="pending_payment",
        payment_provider="stripe",
        service_code="voxbulk",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(existing)
    db.commit()

    sub = CardSubscriptionActivationService.activate_from_payment(
        db, org=org, plan=plan, provider="stripe", payment_intent_id="pi_upsert", billing_interval="monthly"
    )
    assert sub.id == existing.id
    assert sub.status == "active"


def test_stripe_webhook_subscription_checkout_no_wallet_credit(db):
    org, plan = _seed_plan(db)
    org.contact_email = "billing@card-sub.test"
    db.add(org)
    db.commit()

    event = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_webhook_sub",
                "amount_received": 9900,
                "metadata": {
                    "voxbulk_org_id": org.id,
                    "voxbulk_kind": SUBSCRIPTION_CHECKOUT_KIND,
                    "voxbulk_plan_id": plan.id,
                    "voxbulk_billing_interval": "monthly",
                    "voxbulk_service_code": "voxbulk",
                },
            }
        },
    }
    with patch.object(StripeBillingService, "sync_credentials_from_intent") as mock_sync:
        mock_sync.side_effect = lambda db, sub, **kw: sub
        result = StripePaymentService.handle_webhook_event(db, event)
    assert result.get("subscription_activated") is True
    assert db.query(WalletTransaction).count() == 0
    sub = db.query(Subscription).filter(Subscription.org_id == org.id).one()
    assert sub.status == "active"


def test_airwallex_webhook_subscription_checkout_no_wallet_credit(db):
    org, plan = _seed_plan(db)
    org.contact_email = "billing@card-sub.test"
    db.add(org)
    db.commit()

    event = {
        "name": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "int_webhook_sub",
                "captured_amount": 99.0,
                "metadata": {
                    "voxbulk_org_id": org.id,
                    "voxbulk_kind": SUBSCRIPTION_CHECKOUT_KIND,
                    "voxbulk_plan_id": plan.id,
                    "voxbulk_billing_interval": "monthly",
                },
            }
        },
    }
    with patch.object(AirwallexBillingService, "sync_credentials_from_intent") as mock_sync:
        mock_sync.side_effect = lambda db, sub, **kw: sub
        result = AirwallexPaymentService.handle_webhook_event(db, event)
    assert result.get("subscription_activated") is True
    assert db.query(WalletTransaction).count() == 0


def test_verify_intent_rejects_wallet_topup(db):
    org, plan = _seed_plan(db)
    with pytest.raises(Exception, match="not a subscription"):
        CardSubscriptionActivationService.verify_intent_metadata(
            {"voxbulk_kind": "wallet_topup", "voxbulk_org_id": org.id, "voxbulk_plan_id": plan.id},
            org_id=org.id,
            plan_id=plan.id,
        )


def test_stripe_webhook_wallet_topup_still_credits(db):
    org, _plan = _seed_plan(db)
    event = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_topup_only",
                "amount_received": 5000,
                "metadata": {"voxbulk_org_id": org.id, "voxbulk_kind": "wallet_topup"},
            }
        },
    }
    with patch.object(StripePaymentService, "_issue_topup_invoice"):
        result = StripePaymentService.handle_webhook_event(db, event)
    assert result.get("credited") is True
    assert db.query(WalletTransaction).count() == 1
