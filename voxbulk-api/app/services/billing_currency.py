"""Billing currency helpers — VoxBulk bills in GBP, USD, CAD or AUD with explicit per-market prices."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.organisation import Organisation

SUPPORTED_CURRENCIES = ("GBP", "USD", "CAD", "AUD")

CURRENCY_SYMBOLS = {"GBP": "£", "USD": "$", "CAD": "CA$", "AUD": "A$"}

_COUNTRY_CURRENCY = {"GB": "GBP", "US": "USD", "CA": "CAD", "AU": "AUD"}


def normalize_currency(value: str | None) -> str:
    code = str(value or "").strip().upper()[:3]
    return code if code in SUPPORTED_CURRENCIES else "GBP"


def currency_symbol(currency: str | None) -> str:
    return CURRENCY_SYMBOLS.get(normalize_currency(currency), "£")


def money_display(amount_minor: int | None, currency: str | None = "GBP") -> str:
    if amount_minor is None:
        return "Custom"
    sym = currency_symbol(currency)
    return f"{sym}{(int(amount_minor) / 100):,.2f}"


def currency_for_country_code(country_code: str | None) -> str:
    return _COUNTRY_CURRENCY.get(str(country_code or "").strip().upper()[:2], "GBP")


def resolve_org_currency(db: Session, org: Organisation | None, *, persist: bool = False) -> str:
    """Resolve the org billing currency. Once set on the org it is fixed and never re-derived."""
    if org is None:
        return "GBP"
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
