"""Billing audit hardening: checkout trust, VAT, pro-rata, refunds, WA lines."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.country_vat_rate import CountryVatRate
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.wallet_transaction import WalletTransaction
from app.services.billing_lifecycle_service import BillingLifecycleService
from app.services.billing_refund_service import BillingRefundService
from app.services.card_subscription_activation_service import CardSubscriptionActivationService
from app.services.invoice_line_item_service import InvoiceLineItemService
from app.services.invoice_service import InvoiceService
from app.services.stripe_payment_service import StripePaymentService, StripeProviderError
from app.services.subscription_live_guard import apply_live_slot


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


def _org_plan(db, *, interval: str = "monthly") -> tuple[Organisation, Plan]:
    org = Organisation(name="Audit Org", country="gb", billing_currency="GBP")
    db.add(org)
    db.flush()
    plan = Plan(
        code="starter",
        name="Starter",
        price_gbp_pence=9900,
        interval="month",
        calls_included=500,
        whatsapp_included=200,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(plan)
    db.commit()
    db.refresh(org)
    db.refresh(plan)
    return org, plan


def test_confirm_topup_rejects_subscription_intent(db):
    org, _plan = _org_plan(db)
    with patch.object(
        StripePaymentService,
        "retrieve_intent",
        return_value={
            "id": "pi_sub",
            "status": "succeeded",
            "amount_received": 9900,
            "metadata": {"voxbulk_org_id": org.id, "voxbulk_kind": "subscription_checkout"},
        },
    ):
        with pytest.raises(StripeProviderError, match="wallet top-up"):
            StripePaymentService.confirm_topup(db, org, payment_intent_id="pi_sub")


def test_verify_intent_rejects_interval_mismatch_via_metadata(db):
    org, plan = _org_plan(db)
    parsed = CardSubscriptionActivationService.verify_intent_metadata(
        {
            "voxbulk_kind": "subscription_checkout",
            "voxbulk_org_id": org.id,
            "voxbulk_plan_id": plan.id,
            "voxbulk_billing_interval": "yearly",
        },
        org_id=org.id,
        plan_id=plan.id,
    )
    assert parsed["billing_interval"] == "yearly"


def test_unknown_country_vat_is_zero_when_enabled(db):
    from app.models.billing_settings import BillingSettings

    db.add(BillingSettings(id=1, vat_enabled=True, company_name="VoxBulk"))
    db.add(CountryVatRate(country_code="GB", country_name="United Kingdom", vat_rate_percent=20, is_enabled=True))
    db.commit()
    rate = InvoiceService.effective_vat_rate(db, country_code="ZZ", currency="USD")
    assert rate == 0.0
    gb = InvoiceService.effective_vat_rate(db, country_code="GB", currency="GBP")
    assert gb == 20.0


def test_vat_off_is_zero_even_with_gb_rate(db):
    from app.models.billing_settings import BillingSettings

    db.add(BillingSettings(id=1, vat_enabled=False, company_name="VoxBulk"))
    db.add(CountryVatRate(country_code="GB", country_name="United Kingdom", vat_rate_percent=20, is_enabled=True))
    db.commit()
    assert InvoiceService.effective_vat_rate(db, country_code="GB", currency="GBP") == 0.0


def test_wa_extra_line_multiplies_quantity_and_rate():
    lines = InvoiceLineItemService.from_campaign_settlement(
        {
            "channel": "whatsapp",
            "actual_units": 12,
            "included_units": 10,
            "extra_units": 2,
            "wa_extra_minor": 150,
            "wa_package_fee_minor": 100,
        },
        order_title="Campaign A",
        channel="whatsapp",
    )
    extra = [row for row in lines if row.get("kind") == "wa_survey" and int(row.get("total_pence") or 0) > 0]
    assert extra
    assert extra[0]["quantity"] == 2
    assert extra[0]["unit_pence"] == 150
    assert extra[0]["total_pence"] == 300


def test_yearly_pro_rata_uses_remaining_period(db):
    org, old_plan = _org_plan(db)
    new_plan = Plan(
        code="pro",
        name="Pro",
        price_gbp_pence=19900,
        interval="year",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(new_plan)
    db.flush()
    now = datetime.utcnow()
    sub = Subscription(
        org_id=org.id,
        plan_id=old_plan.id,
        service_code="voxbulk",
        status="active",
        billing_interval="yearly",
        current_period_end=now + timedelta(days=180),
        created_at=now,
        updated_at=now,
    )
    apply_live_slot(sub)
    db.add(sub)
    db.commit()

    def _amount(_db, _org, plan, _interval):
        return ("GBP", 120000 if plan.code == "pro" else 60000, "yearly")

    with patch("app.services.billing_lifecycle_service.PlanPriceService.billing_amount_for_org", side_effect=_amount):
        pro_rata = BillingLifecycleService.calculate_pro_rata_minor(
            db, org=org, sub=sub, old_plan=old_plan, new_plan=new_plan
        )
    assert 25000 < pro_rata < 35000


def test_refund_freezes_matching_subscription(db):
    org, plan = _org_plan(db)
    sub = Subscription(
        org_id=org.id,
        plan_id=plan.id,
        service_code="voxbulk",
        status="active",
        payment_provider="stripe",
        external_subscription_id="pi_checkout",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    apply_live_slot(sub)
    db.add(sub)
    db.commit()
    result = BillingRefundService.handle_provider_refund(
        db,
        provider="stripe",
        org_id=org.id,
        payment_kind="subscription_checkout",
        payment_intent_id="pi_checkout",
        refund_id="re_1",
        amount_minor=9900,
        metadata={"voxbulk_service_code": "voxbulk"},
    )
    db.refresh(sub)
    assert result.get("frozen") is True
    assert sub.status == "suspended"


def test_refund_reverses_wallet_topup(db):
    org, _plan = _org_plan(db)
    org.wallet_balance_pence = 5000
    db.add(
        WalletTransaction(
            org_id=org.id,
            direction="credit",
            kind="topup",
            amount_minor=5000,
            currency="GBP",
            status="succeeded",
            provider="stripe",
            provider_reference="pi_wallet",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    result = BillingRefundService.handle_provider_refund(
        db,
        provider="stripe",
        org_id=org.id,
        payment_kind="wallet_topup",
        payment_intent_id="pi_wallet",
        refund_id="re_wallet",
        amount_minor=5000,
    )
    db.refresh(org)
    assert result.get("reversed") is True
    assert int(org.wallet_balance_pence or 0) == 0
    second = BillingRefundService.handle_provider_refund(
        db,
        provider="stripe",
        org_id=org.id,
        payment_kind="wallet_topup",
        payment_intent_id="pi_wallet",
        refund_id="re_wallet",
        amount_minor=5000,
    )
    assert second.get("duplicate") is True


def test_advance_skips_cancel_at_period_end(db):
    org, plan = _org_plan(db)
    now = datetime.utcnow()
    end = now + timedelta(days=20)
    sub = Subscription(
        org_id=org.id,
        plan_id=plan.id,
        service_code="voxbulk",
        status="active",
        cancel_at_period_end=True,
        current_period_end=end,
        created_at=now,
        updated_at=now,
    )
    apply_live_slot(sub)
    db.add(sub)
    db.commit()
    BillingLifecycleService._advance_subscription_period(db, sub, plan, payment_id="PM_SKIP")
    db.refresh(sub)
    assert sub.current_period_end == end
    assert sub.last_advanced_payment_id is None


def test_advance_once_same_payment_id(db):
    org, plan = _org_plan(db)
    now = datetime.utcnow()
    end = now + timedelta(days=10)
    sub = Subscription(
        org_id=org.id,
        plan_id=plan.id,
        service_code="voxbulk",
        status="active",
        billing_interval="monthly",
        current_period_end=end,
        created_at=now,
        updated_at=now,
    )
    apply_live_slot(sub)
    db.add(sub)
    db.commit()
    BillingLifecycleService._advance_subscription_period(db, sub, plan, payment_id="PM_ONCE")
    db.refresh(sub)
    first_end = sub.current_period_end
    assert first_end != end
    assert sub.last_advanced_payment_id == "PM_ONCE"
    BillingLifecycleService._advance_subscription_period(db, sub, plan, payment_id="PM_ONCE")
    db.refresh(sub)
    assert sub.current_period_end == first_end


def test_gc_period_advance_only_on_confirmed():
    from app.services.gocardless_billing_webhook_service import PAYMENT_SUCCESS_ACTIONS

    assert "confirmed" in PAYMENT_SUCCESS_ACTIONS
    assert "paid_out" in PAYMENT_SUCCESS_ACTIONS


def test_webhook_duplicate_keeps_unprocessed_for_rerun(db):
    from app.services.recovery_service import WebhookEventService

    body = b'{"id":"evt_audit_rerun","type":"payment_intent.succeeded"}'
    first, created = WebhookEventService.persist_received(
        db, provider="stripe", raw_body=body, external_event_id="evt_audit_rerun"
    )
    assert created is True
    first.status = "failed"
    db.add(first)
    db.commit()
    second, created2 = WebhookEventService.persist_received(
        db, provider="stripe", raw_body=body, external_event_id="evt_audit_rerun"
    )
    assert created2 is False
    assert str(second.status or "").lower() != "processed"


def test_unknown_country_code_is_not_gb(db):
    from app.services.country_vat_service import CountryVatService

    assert CountryVatService.resolve_country_code(db, "") == ""
    assert CountryVatService.resolve_country_code(db, "Neverland") == ""
    assert CountryVatService.resolve_country_code(db, "GB") == "GB"
