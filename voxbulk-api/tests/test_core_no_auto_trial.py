"""Core voxbulk must not auto-apply plan.trial_days_default; Smart Card keeps 30."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.services.smart_card.billing_service import SmartCardBillingService
from app.services.stripe_subscription_service import StripeSubscriptionService


def test_core_stripe_ignores_plan_trial_days_default_without_promo():
    org = Organisation(id=str(uuid.uuid4()), name="Org", billing_currency="GBP")
    plan = Plan(
        id=str(uuid.uuid4()),
        code="starter",
        name="Starter",
        service_kind="voxbulk",
        trial_days_default=14,
    )
    db = MagicMock()

    with (
        patch(
            "app.services.stripe_payment_service.StripePaymentService.is_available",
            return_value=True,
        ),
        patch("app.services.billing_currency.charge_currency_for_org", return_value="GBP"),
        patch(
            "app.services.custom_packages_service.CustomPackagesService.assert_checkout_allowed",
        ),
        patch(
            "app.services.plan_price_service.PlanPriceService.billing_amount_for_org",
            return_value=("GBP", 9900, "monthly"),
        ),
        patch(
            "app.services.promo_discount_service.PromoDiscountService.peek_amount",
            return_value={
                "amount_minor": 9900,
                "original_amount_minor": 9900,
                "discount_applied": False,
                "trial_days": 0,
            },
        ),
        patch(
            "app.services.stripe_payment_service.StripePaymentService.create_subscription_checkout_intent",
            return_value={
                "client_secret": "pi_sec",
                "payment_intent_id": "pi_paid",
                "publishable_key": "pk_test",
            },
        ) as create_pi,
        patch(
            "app.services.stripe_payment_service.StripePaymentService.create_subscription_setup_intent",
        ) as create_si,
    ):
        result = StripeSubscriptionService.start_subscription_checkout(
            db,
            org=org,
            plan=plan,
            user_email="a@example.com",
            billing_interval="monthly",
            service_code="voxbulk",
        )

    create_si.assert_not_called()
    create_pi.assert_called_once()
    assert int(result.get("trial_days") or 0) == 0
    assert result.get("mode") != "setup"
    assert int(result.get("amount_minor") or 0) == 9900


def test_core_stripe_promo_trial_still_uses_setup_intent():
    org = Organisation(id=str(uuid.uuid4()), name="Org", billing_currency="GBP")
    plan = Plan(
        id=str(uuid.uuid4()),
        code="starter",
        name="Starter",
        service_kind="voxbulk",
        trial_days_default=0,
    )
    db = MagicMock()

    with (
        patch(
            "app.services.stripe_payment_service.StripePaymentService.is_available",
            return_value=True,
        ),
        patch("app.services.billing_currency.charge_currency_for_org", return_value="GBP"),
        patch(
            "app.services.custom_packages_service.CustomPackagesService.assert_checkout_allowed",
        ),
        patch(
            "app.services.plan_price_service.PlanPriceService.billing_amount_for_org",
            return_value=("GBP", 9900, "monthly"),
        ),
        patch(
            "app.services.promo_discount_service.PromoDiscountService.peek_amount",
            return_value={
                "amount_minor": 0,
                "original_amount_minor": 9900,
                "discount_applied": True,
                "trial_days": 7,
                "discount_type": "trial_days",
            },
        ),
        patch(
            "app.services.stripe_payment_service.StripePaymentService.create_subscription_setup_intent",
            return_value={
                "client_secret": "seti_sec",
                "setup_intent_id": "seti_x",
                "publishable_key": "pk_test",
            },
        ) as create_si,
    ):
        result = StripeSubscriptionService.start_subscription_checkout(
            db,
            org=org,
            plan=plan,
            user_email="a@example.com",
            billing_interval="monthly",
            service_code="voxbulk",
        )

    create_si.assert_called_once()
    assert result.get("mode") == "setup"
    assert int(result.get("trial_days") or 0) == 7


def test_smart_card_resolve_trial_still_defaults_to_30():
    plan = Plan(id=str(uuid.uuid4()), code="smart_card_seat", name="SC", trial_days_default=0)
    db = MagicMock()
    with patch(
        "app.services.promo_discount_service.PromoDiscountService.peek_amount",
        return_value={"trial_days": 0, "discount_applied": False, "amount_minor": 1},
    ):
        assert SmartCardBillingService.resolve_trial_days(db, org_id="org", plan=plan) == 30
