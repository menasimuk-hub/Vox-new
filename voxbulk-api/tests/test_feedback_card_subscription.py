"""Tests for Customer Feedback card subscription checkout (GCC / non-GoCardless)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.customer_feedback import FEEDBACK_SERVICE_CODE, FeedbackPackage
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.services.customer_feedback.billing_service import FeedbackBillingError, FeedbackBillingService


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


def _seed_ae_org_with_feedback_plan(db) -> tuple[Organisation, Plan, FeedbackPackage]:
    org = Organisation(
        name="Gulf Clinic",
        country="ae",
        billing_currency="USD",
        contact_email="bill@gulf.test",
    )
    db.add(org)
    db.flush()
    plan = Plan(
        code="cf_starter_ae",
        name="Feedback Starter",
        price_gbp_pence=0,
        interval="month",
        service_kind=FEEDBACK_SERVICE_CODE,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(plan)
    db.flush()
    pkg = FeedbackPackage(
        id="pkg-ae-1",
        plan_id=plan.id,
        market_zone="us",
        max_locations=1,
        wa_units_included=100,
        web_units_included=50,
        display_order=1,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(pkg)
    db.commit()
    db.refresh(org)
    db.refresh(plan)
    return org, plan, pkg


@patch("app.services.payment_provider_router.PaymentProviderRouter.primary_subscription_provider", return_value="airwallex")
@patch("app.services.airwallex_subscription_service.AirwallexSubscriptionService.start_subscription_checkout")
def test_feedback_start_card_signup_routes_airwallex(mock_start, _provider, db):
    org, plan, _pkg = _seed_ae_org_with_feedback_plan(db)
    mock_start.return_value = {
        "provider": "airwallex",
        "currency": "USD",
        "amount_minor": 9900,
        "billing_interval": "monthly",
        "client_secret": "sec_test",
        "intent_id": "int_test",
        "plan_id": plan.id,
    }

    result = FeedbackBillingService.start_card_signup(
        db,
        org=org,
        user_email="owner@gulf.test",
        plan_id=plan.id,
        billing_interval="monthly",
    )

    assert result["provider"] == "airwallex"
    mock_start.assert_called_once()
    assert mock_start.call_args.kwargs["service_code"] == FEEDBACK_SERVICE_CODE


@patch("app.services.payment_provider_router.PaymentProviderRouter.primary_subscription_provider", return_value="gocardless")
def test_feedback_start_card_rejects_gocardless_region(_provider, db):
    org, plan, _pkg = _seed_ae_org_with_feedback_plan(db)
    org.country = "gb"
    db.add(org)
    db.commit()

    with pytest.raises(FeedbackBillingError, match="GoCardless"):
        FeedbackBillingService.start_card_signup(
            db,
            org=org,
            user_email="owner@test.com",
            plan_id=plan.id,
        )
