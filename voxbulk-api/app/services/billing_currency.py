"""Billing currency helpers — VoxBulk bills in GBP, EUR, USD, CAD, AUD with explicit per-market prices."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation

SUPPORTED_CURRENCIES = ("GBP", "EUR", "USD", "CAD", "AUD")

CURRENCY_SYMBOLS = {"GBP": "£", "EUR": "€", "USD": "$", "CAD": "CA$", "AUD": "A$"}

# All 27 EU member states bill in EUR.
EU_MEMBER_STATES = frozenset(
    {
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
    }
)

_COUNTRY_CURRENCY = {"GB": "GBP", "US": "USD", "CA": "CAD", "AU": "AUD"}
_DEFAULT_CURRENCY = "USD"


def normalize_currency(value: str | None) -> str:
    code = str(value or "").strip().upper()[:3]
    return code if code in SUPPORTED_CURRENCIES else _DEFAULT_CURRENCY


def currency_symbol(currency: str | None) -> str:
    return CURRENCY_SYMBOLS.get(normalize_currency(currency), "$")


def money_display(amount_minor: int | None, currency: str | None = "GBP") -> str:
    if amount_minor is None:
        return "Custom"
    sym = currency_symbol(currency)
    return f"{sym}{(int(amount_minor) / 100):,.2f}"


def currency_for_country_code(country_code: str | None) -> str:
    code = str(country_code or "").strip().upper()[:2]
    if code in EU_MEMBER_STATES:
        return "EUR"
    return _COUNTRY_CURRENCY.get(code, _DEFAULT_CURRENCY)


def billing_currency_is_locked(db: Session, org: Organisation | None) -> bool:
    """True once the org has billing activity — currency must not change on profile country edit."""
    if org is None:
        return False
    from app.models.billing_invoice import BillingInvoice
    from app.models.subscription import Subscription
    from app.models.wallet_transaction import WalletTransaction

    wallet_count = int(
        db.scalar(
            select(func.count())
            .select_from(WalletTransaction)
            .where(WalletTransaction.org_id == org.id)
        )
        or 0
    )
    if wallet_count > 0:
        return True
    paid_count = int(
        db.scalar(
            select(func.count())
            .select_from(BillingInvoice)
            .where(BillingInvoice.org_id == org.id, BillingInvoice.status == "paid")
        )
        or 0
    )
    if paid_count > 0:
        return True
    sub = db.execute(
        select(Subscription)
        .where(Subscription.org_id == org.id, Subscription.first_payment_at.isnot(None))
        .limit(1)
    ).scalar_one_or_none()
    return sub is not None


def resolve_org_currency(db: Session, org: Organisation | None, *, persist: bool = False) -> str:
    """Resolve the org billing currency. Once set on the org it is fixed and never re-derived."""
    if org is None:
        return _DEFAULT_CURRENCY
    existing = str(getattr(org, "billing_currency", None) or "").strip().upper()
    if existing in SUPPORTED_CURRENCIES:
        return existing
    from app.services.country_vat_service import CountryVatService

    code = CountryVatService.resolve_org_country_code(db, org)
    currency = currency_for_country_code(code)
    if persist:
        org.billing_currency = currency
        db.add(org)
        db.commit()
    return currency
