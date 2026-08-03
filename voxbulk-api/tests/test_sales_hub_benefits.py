"""Sales Hub benefits helpers and payment router near-term policy."""

from __future__ import annotations

from app.services.billing_currency import currency_for_country_code
from app.services.sales_hub_benefits import (
    benefit_summaries,
    default_promo_benefits,
    normalize_commission_tiers,
    normalize_promo_benefits,
    parse_promo_benefits,
)


class _FakeRep:
    def __init__(self, **kwargs):
        self.country = kwargs.get("country", "GB")
        self.currency = kwargs.get("currency")
        self.promo_benefits_json = kwargs.get("promo_benefits_json")
        self.commission_tiers_json = kwargs.get("commission_tiers_json")
        self.partner_terms_json = kwargs.get("partner_terms_json")
        self.commission_type = kwargs.get("commission_type", "month2")
        self.commission_pct = kwargs.get("commission_pct", 15)
        self.commission_fixed_minor = kwargs.get("commission_fixed_minor", 0)


def test_currency_for_sales_locations():
    assert currency_for_country_code("GB") == "GBP"
    assert currency_for_country_code("DE") == "EUR"
    assert currency_for_country_code("US") == "USD"
    assert currency_for_country_code("AE") == "USD"


def test_default_promo_includes_voucher():
    b = default_promo_benefits(voucher_enabled=True, voucher_minor=2000)
    assert b["wallet_voucher"]["enabled"] is True
    assert b["wallet_voucher"]["amount_minor"] == 2000
    assert "ai_interview" in b["services"]


def test_normalize_promo_benefits_services():
    raw = {
        "wallet_voucher": {"enabled": True, "amount_minor": 2500},
        "services": {
            "ai_interview": {"enabled": True, "kind": "percent_discount", "value": 20},
            "voxbulk_expo": {"enabled": True, "kind": "free_package_days", "value": 3},
        },
    }
    b = normalize_promo_benefits(raw)
    assert b["wallet_voucher"]["amount_minor"] == 2500
    assert b["services"]["ai_interview"]["enabled"] is True
    assert b["services"]["voxbulk_expo"]["kind"] == "free_package_days"
    lines = benefit_summaries(b, currency="EUR")
    assert any("Wallet voucher" in x for x in lines)
    assert any("20%" in x for x in lines)


def test_commission_tiers_normalize():
    tiers = normalize_commission_tiers(
        [
            {"month": 2, "enabled": True, "kind": "percent", "value": 10},
            {"month": 3, "enabled": True, "kind": "percent", "value": 5},
            {"month": 4, "enabled": False, "kind": "percent", "value": 5},
        ]
    )
    assert tiers[0]["month"] == 2 and tiers[0]["enabled"]
    assert tiers[1]["enabled"]
    assert not tiers[2]["enabled"]


def test_parse_legacy_rep_defaults_voucher():
    rep = _FakeRep(promo_benefits_json=None)
    b = parse_promo_benefits(rep)
    assert b["wallet_voucher"]["enabled"] is True


def test_payment_router_prefers_stripe_over_airwallex_when_no_gc(monkeypatch):
    from app.services import payment_provider_router as ppr

    class FakeOrg:
        billing_payment_provider = None
        country = "AE"

    class FakeDb:
        pass

    monkeypatch.setattr(
        ppr.PaymentProviderRouter,
        "org_country_code",
        staticmethod(lambda db, org: "AE"),
    )

    class FakeGC:
        @staticmethod
        def payment_options(db):
            return {"gocardless_available": False}

    class FakeStripe:
        @staticmethod
        def is_available(db):
            return True

    class FakeAwx:
        @staticmethod
        def is_available(db):
            return True

    monkeypatch.setattr("app.services.gocardless_service.BillingService", FakeGC)
    monkeypatch.setattr("app.services.stripe_payment_service.StripePaymentService", FakeStripe)
    monkeypatch.setattr("app.services.airwallex_payment_service.AirwallexPaymentService", FakeAwx)

    assert ppr.PaymentProviderRouter.primary_subscription_provider(FakeDb(), FakeOrg()) == "stripe"
