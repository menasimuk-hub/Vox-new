"""Resolve organisation country + billing currency for admin control center and billing flows."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.services.billing_currency import currency_symbol, money_display, resolve_org_currency
from app.services.country_vat_service import CountryVatService
from app.services.market_zone import country_to_zone, zone_label
from app.services.usage_wallet_service import UsageWalletService


def sync_org_country_code(db: Session, org: Organisation, *, commit: bool = True) -> str:
    code = CountryVatService.resolve_org_country_code(db, org)
    if getattr(org, "country_code", None) != code:
        org.country_code = code
        db.add(org)
        if commit:
            db.commit()
            db.refresh(org)
    return code


def resolve_org_billing_profile(db: Session, org: Organisation | None) -> dict[str, Any]:
    if org is None:
        return {
            "country": None,
            "country_code": "GB",
            "market_zone": "gb",
            "market_label": zone_label("gb"),
            "billing_currency": "GBP",
            "currency_symbol": "£",
            "billing_email": None,
            "contact_email": None,
            "payment_method": None,
        }

    country_code = str(getattr(org, "country_code", None) or CountryVatService.resolve_org_country_code(db, org)).upper()[:2]
    market_zone = country_to_zone(org.country or country_code)
    currency = resolve_org_currency(db, org)
    billing_email = UsageWalletService.get_org_billing_email(db, org.id) or org.contact_email

    sub_payment = None
    from sqlalchemy import select

    from app.models.subscription import Subscription

    sub = db.execute(
        select(Subscription)
        .where(Subscription.org_id == org.id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if sub is not None:
        sub_payment = getattr(sub, "payment_provider", None) or getattr(sub, "provider", None)

    return {
        "country": org.country,
        "country_code": country_code,
        "market_zone": market_zone,
        "market_label": zone_label(market_zone),
        "billing_currency": currency,
        "currency_symbol": currency_symbol(currency),
        "wallet_display": money_display(int(org.wallet_balance_pence or 0), currency),
        "billing_email": billing_email,
        "contact_email": org.contact_email,
        "contact_name": org.contact_name,
        "contact_phone": org.contact_phone,
        "payment_method": sub_payment,
        "allow_overage": bool(getattr(org, "allow_overage", True)),
        "billing_currency_locked": bool(str(getattr(org, "billing_currency", None) or "").strip()),
    }


def money_for_org(db: Session, org: Organisation | None, amount_minor: int) -> str:
    currency = resolve_org_currency(db, org) if org else "GBP"
    return money_display(amount_minor, currency)
