"""Live checkout quote: catalog → promo peek → VAT → total display."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.country_vat_service import CountryVatService
from app.services.promo_discount_service import PromoDiscountService, normalize_service_kind


class CheckoutQuoteService:
    @staticmethod
    def quote(
        db: Session,
        *,
        org: Organisation,
        service_kind: str,
        amount_minor: int,
    ) -> dict[str, Any]:
        sk = normalize_service_kind(service_kind)
        catalog = max(0, int(amount_minor or 0))
        currency = resolve_org_currency(db, org)
        country = CountryVatService.resolve_org_country_code(db, org)
        rate, country_name = CountryVatService.get_rate(db, country)

        peeked = PromoDiscountService.peek_amount(
            db, org_id=org.id, service_kind=sk, amount_minor=catalog
        )
        discounted = max(0, int(peeked.get("amount_minor") or catalog))
        discount_minor = max(0, catalog - discounted)
        inclusive = CountryVatService.is_vat_inclusive_pricing(db, country, currency)

        if inclusive and rate > 0:
            net_minor, vat_minor = CountryVatService.split_gross_pence(discounted, rate)
            total_minor = discounted
            vat_mode = "inclusive"
        else:
            net_minor = discounted
            vat_minor = CountryVatService.compute_tax(net_minor, rate) if rate > 0 else 0
            total_minor = net_minor + vat_minor
            vat_mode = "exclusive"

        return {
            "ok": True,
            "service_kind": sk,
            "currency": currency,
            "country_code": country,
            "country_name": country_name,
            "catalog_minor": catalog,
            "discount_minor": discount_minor,
            "discount_applied": bool(peeked.get("discount_applied")),
            "net_minor": net_minor,
            "vat_rate_percent": float(rate or 0),
            "vat_minor": vat_minor,
            "vat_mode": vat_mode,
            "total_minor": total_minor,
            "catalog_display": money_display(catalog, currency),
            "discount_display": money_display(discount_minor, currency) if discount_minor else None,
            "net_display": money_display(net_minor, currency),
            "vat_display": money_display(vat_minor, currency) if vat_minor else None,
            "total_display": money_display(total_minor, currency),
            "amount_note": (
                f"Includes VAT ({rate:g}%)"
                if vat_mode == "inclusive" and vat_minor
                else (
                    f"Ex-VAT {money_display(net_minor, currency)}"
                    + (f" + VAT {money_display(vat_minor, currency)} ({rate:g}%)" if vat_minor else "")
                    if vat_mode == "exclusive"
                    else "Ex-VAT. VAT may apply at checkout."
                )
            ),
        }
