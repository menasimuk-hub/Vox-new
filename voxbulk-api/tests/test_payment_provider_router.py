"""Country-based subscription payment provider routing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.organisation import Organisation
from app.services.payment_provider_router import PaymentProviderRouter


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


def _org(db, *, country: str = "gb", provider: str | None = None) -> Organisation:
    org = Organisation(name="Routing Org", country=country, billing_currency="GBP")
    if provider:
        org.billing_payment_provider = provider
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@patch("app.services.stripe_payment_service.StripePaymentService.is_available", return_value=True)
@patch("app.services.airwallex_payment_service.AirwallexPaymentService.is_available", return_value=True)
@patch("app.services.gocardless_service.BillingService.payment_options")
def test_gb_org_routes_to_gocardless_when_available(mock_gc, _awx, _stripe, db):
    mock_gc.return_value = {"gocardless_available": True}
    org = _org(db, country="gb")
    assert PaymentProviderRouter.primary_subscription_provider(db, org) == "gocardless"


@patch("app.services.stripe_payment_service.StripePaymentService.is_available", return_value=True)
@patch("app.services.airwallex_payment_service.AirwallexPaymentService.is_available", return_value=True)
@patch("app.services.gocardless_service.BillingService.payment_options")
def test_ae_org_routes_to_airwallex(mock_gc, _awx, _stripe, db):
    mock_gc.return_value = {"gocardless_available": True}
    org = _org(db, country="ae")
    assert PaymentProviderRouter.primary_subscription_provider(db, org) == "airwallex"


@patch("app.services.stripe_payment_service.StripePaymentService.is_available", return_value=True)
@patch("app.services.airwallex_payment_service.AirwallexPaymentService.is_available", return_value=False)
@patch("app.services.gocardless_service.BillingService.payment_options")
def test_non_gc_country_falls_back_to_stripe_when_airwallex_off(mock_gc, _awx, _stripe, db):
    mock_gc.return_value = {"gocardless_available": False}
    org = _org(db, country="ae")
    assert PaymentProviderRouter.primary_subscription_provider(db, org) == "stripe"


@patch("app.services.stripe_payment_service.StripePaymentService.is_available", return_value=True)
@patch("app.services.airwallex_payment_service.AirwallexPaymentService.is_available", return_value=True)
@patch("app.services.gocardless_service.BillingService.payment_options")
def test_admin_override_wins(mock_gc, _awx, _stripe, db):
    mock_gc.return_value = {"gocardless_available": True}
    org = _org(db, country="gb", provider="airwallex")
    assert PaymentProviderRouter.primary_subscription_provider(db, org) == "airwallex"
    explain = PaymentProviderRouter.routing_explain(db, org)
    assert explain["org_override"] == "airwallex"
    assert "Admin override" in explain["reason"]
