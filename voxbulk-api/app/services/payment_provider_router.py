"""Route subscription and overage collection by org country / provider availability."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.services.billing_currency import resolve_org_currency
from app.services.country_vat_service import CountryVatService

# GoCardless-supported payer markets (bank debit).
GOCARDLESS_COUNTRY_CODES = frozenset(
    {
        "GB",
        "US",
        "CA",
        "AU",
        *{
            "AT",
            "BE",
            "BG",
            "HR",
            "CY",
            "CZ",
            "DK",
            "EE",
            "FI",
            "FR",
            "DE",
            "GR",
            "HU",
            "IE",
            "IT",
            "LV",
            "LT",
            "LU",
            "MT",
            "NL",
            "PL",
            "PT",
            "RO",
            "SK",
            "SI",
            "ES",
            "SE",
            "NO",
            "CH",
            "IS",
            "NZ",
        },
    }
)

# Gulf / non-GC → Airwallex card subscriptions (USD pricing).
AIRWALLEX_SUBSCRIPTION_COUNTRY_CODES = frozenset({"AE", "SA", "QA", "BH", "KW", "OM"})


class PaymentProviderRouter:
    @staticmethod
    def org_country_code(db: Session, org: Organisation | None) -> str:
        if org is None:
            return "US"
        return CountryVatService.resolve_org_country_code(db, org)

    @staticmethod
    def primary_subscription_provider(db: Session, org: Organisation | None) -> str:
        """gocardless | airwallex | stripe — country-based with optional org override."""
        if org is None:
            return "stripe"
        forced = str(getattr(org, "billing_payment_provider", None) or "").strip().lower()
        if forced in {"gocardless", "airwallex", "stripe"}:
            return forced

        from app.services.airwallex_payment_service import AirwallexPaymentService
        from app.services.gocardless_service import BillingService
        from app.services.stripe_payment_service import StripePaymentService

        code = PaymentProviderRouter.org_country_code(db, org)
        gc_opts = BillingService.payment_options(db)
        gc_available = bool(gc_opts.get("gocardless_available"))
        awx_available = AirwallexPaymentService.is_available(db)
        stripe_available = StripePaymentService.is_available(db)

        if code in GOCARDLESS_COUNTRY_CODES and gc_available:
            return "gocardless"
        if awx_available:
            return "airwallex"
        if stripe_available:
            return "stripe"
        if gc_available:
            return "gocardless"
        return "stripe"

    @staticmethod
    def routing_explain(db: Session, org: Organisation | None) -> dict:
        """Human-readable routing decision for admin / debugging."""
        from app.services.airwallex_payment_service import AirwallexPaymentService
        from app.services.gocardless_service import BillingService
        from app.services.stripe_payment_service import StripePaymentService

        code = PaymentProviderRouter.org_country_code(db, org)
        gc_opts = BillingService.payment_options(db)
        gc_available = bool(gc_opts.get("gocardless_available"))
        awx_available = AirwallexPaymentService.is_available(db)
        stripe_available = StripePaymentService.is_available(db)
        forced = str(getattr(org, "billing_payment_provider", None) or "").strip().lower() if org else ""
        primary = PaymentProviderRouter.primary_subscription_provider(db, org)
        if forced in {"gocardless", "airwallex", "stripe"}:
            reason = f"Admin override: {forced}"
        elif code in GOCARDLESS_COUNTRY_CODES and gc_available:
            reason = f"Country {code} supports GoCardless Direct Debit"
        elif awx_available:
            reason = f"Country {code} — card checkout via Airwallex (GoCardless unavailable or unsupported)"
        elif stripe_available:
            reason = f"Country {code} — card checkout via Stripe"
        elif gc_available:
            reason = "GoCardless fallback (only configured provider)"
        else:
            reason = "No payment provider configured — defaulting to Stripe"
        return {
            "primary_provider": primary,
            "country_code": code,
            "reason": reason,
            "gocardless_country": code in GOCARDLESS_COUNTRY_CODES,
            "gocardless_available": gc_available,
            "airwallex_available": awx_available,
            "stripe_available": stripe_available,
            "org_override": forced or None,
            "policy": "GoCardless when org country supports it and GoCardless is enabled; otherwise Airwallex card checkout.",
        }

    @staticmethod
    def subscription_options(db: Session, org: Organisation | None) -> dict:
        primary = PaymentProviderRouter.primary_subscription_provider(db, org)
        from app.services.airwallex_payment_service import AirwallexPaymentService
        from app.services.gocardless_service import BillingService
        from app.services.stripe_payment_service import StripePaymentService

        gc = BillingService.payment_options(db)
        return {
            "primary_provider": primary,
            "currency": resolve_org_currency(db, org),
            "country_code": PaymentProviderRouter.org_country_code(db, org),
            "gocardless_available": bool(gc.get("gocardless_available")),
            "airwallex_available": AirwallexPaymentService.is_available(db),
            "stripe_available": StripePaymentService.is_available(db),
            "stripe_backup": primary != "stripe" and StripePaymentService.is_available(db),
        }
