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
        """gocardless | airwallex | stripe"""
        if org is None:
            return "stripe"
        forced = str(getattr(org, "billing_payment_provider", None) or "").strip().lower()
        if forced in {"gocardless", "airwallex", "stripe"}:
            return forced
        code = PaymentProviderRouter.org_country_code(db, org)
        if code in AIRWALLEX_SUBSCRIPTION_COUNTRY_CODES:
            from app.services.airwallex_payment_service import AirwallexPaymentService

            if AirwallexPaymentService.is_available(db):
                return "airwallex"
            from app.services.stripe_payment_service import StripePaymentService

            return "stripe" if StripePaymentService.is_available(db) else "airwallex"
        if code in GOCARDLESS_COUNTRY_CODES:
            return "gocardless"
        from app.services.airwallex_payment_service import AirwallexPaymentService

        if AirwallexPaymentService.is_available(db):
            return "airwallex"
        from app.services.stripe_payment_service import StripePaymentService

        return "stripe" if StripePaymentService.is_available(db) else "gocardless"

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
