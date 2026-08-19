"""Sales Hub benefits helpers and payment router near-term policy."""

from __future__ import annotations

from app.services.billing_currency import currency_for_country_code
from app.services.sales_hub_benefits import (
    benefit_summaries,
    default_promo_benefits,
    normalize_commission_tiers,
    normalize_promo_benefits,
    parse_promo_benefits,
    signup_benefit_lines,
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
            "customer_feedback": {"enabled": True, "kind": "fixed_topup", "value": 1500},
            "voxbulk_expo": {"enabled": True, "kind": "free_package_days", "value": 3},
        },
    }
    b = normalize_promo_benefits(raw)
    assert b["wallet_voucher"]["amount_minor"] == 2500
    assert b["services"]["ai_interview"]["enabled"] is True
    assert b["services"]["customer_feedback"]["kind"] == "fixed_topup"
    assert b["services"]["customer_feedback"]["value"] == 1500
    assert b["services"]["voxbulk_expo"]["kind"] == "free_package_days"
    lines = benefit_summaries(b, currency="EUR")
    assert any("wallet credit" in x.lower() for x in lines)
    assert any("20%" in x for x in lines)
    assert any("top-up" in x for x in lines)


def test_commission_tiers_normalize():
    tiers = normalize_commission_tiers(
        [
            {"month": 1, "enabled": True, "kind": "percent", "value": 8},
            {"month": 2, "enabled": True, "kind": "percent", "value": 10},
            {"month": 3, "enabled": True, "kind": "percent", "value": 5},
            {"month": 4, "enabled": False, "kind": "percent", "value": 5},
            {"month": 6, "enabled": True, "kind": "fixed", "value": 500},
        ]
    )
    assert [t["month"] for t in tiers] == [1, 2, 3, 4, 5, 6]
    assert tiers[0]["month"] == 1 and tiers[0]["enabled"] and tiers[0]["value"] == 8
    assert tiers[1]["enabled"] and tiers[1]["value"] == 10
    assert tiers[2]["enabled"]
    assert not tiers[3]["enabled"]
    assert not tiers[4]["enabled"]  # month 5 missing → disabled
    assert tiers[5]["enabled"] and tiers[5]["kind"] == "fixed" and tiers[5]["value"] == 500


def test_smart_card_in_promo_normalize():
    raw = {
        "wallet_voucher": {"enabled": False, "amount_minor": 0},
        "services": {
            "smart_card": {"enabled": True, "kind": "percent_discount", "value": 15},
        },
    }
    b = normalize_promo_benefits(raw)
    assert "smart_card" in b["services"]
    assert b["services"]["smart_card"]["enabled"] is True
    assert b["services"]["smart_card"]["kind"] == "percent_discount"
    lines = benefit_summaries(b, currency="GBP")
    assert any("Smart Card" in x or "smart" in x.lower() for x in lines)


def test_signup_benefit_lines_lists_wallet_expo_and_smart_card():
    b = default_promo_benefits()
    b["services"]["voxbulk_expo"] = {"enabled": True, "kind": "free_package_days", "value": 3}
    b["services"]["smart_card"] = {"enabled": True, "kind": "free_days", "value": 30}
    lines = signup_benefit_lines(b, currency="GBP")
    joined = " ".join(lines).lower()
    assert any("welcome wallet credit" in x.lower() for x in lines)
    assert "expo" in joined
    assert "smart card" in joined
    assert any("3" in x for x in lines)
    assert any("30" in x for x in lines)


def test_signup_message_overrides_auto_lines():
    lines = signup_benefit_lines({"signup_message": "Free Expo\nSmart Card 30 days"}, currency="GBP")
    assert lines == ["Free Expo", "Smart Card 30 days"]


def test_commission_mode_helpers():
    from app.services.sales_hub_benefits import normalize_commission_mode, set_commission_extras

    assert normalize_commission_mode("one_time_only") == "one_time_only"
    assert normalize_commission_mode("bogus") == "commission_only"
    rep = _FakeRep()
    rep.commission_mode = "commission_only"
    rep.one_time_bonus_minor = 0
    set_commission_extras(rep, mode="one_time_plus_commission", one_time_bonus_minor=5000)
    assert rep.commission_mode == "one_time_plus_commission"
    assert rep.one_time_bonus_minor == 5000


def test_set_commission_tiers_preserves_partner_percent():
    from app.services.sales_hub_benefits import set_commission_tiers

    rep = _FakeRep(commission_type="percent", commission_pct=12)
    rep.kind = "partner_channel"
    set_commission_tiers(
        rep,
        [{"month": 2, "enabled": True, "kind": "percent", "value": 20}],
        preserve_partner_type=True,
    )
    assert rep.commission_type == "percent"
    assert float(rep.commission_pct) == 20.0


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
