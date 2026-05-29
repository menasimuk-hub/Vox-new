"""Map organisation country to dashboard pricing market (GBP, CAD, AUD, USD)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.services.country_vat_service import CountryVatService
from app.services.voxbulk_pricing_service import MARKETS, MARKET_SYMBOLS

_COUNTRY_CODE_TO_MARKET: dict[str, str] = {
    "GB": "gbp",
    "UK": "gbp",
    "CA": "cad",
    "AU": "aud",
    "US": "usd",
    "NZ": "aud",
    "SG": "usd",
    "IE": "gbp",
}


class PricingMarketService:
    @staticmethod
    def market_for_country_code(country_code: str | None) -> str:
        code = str(country_code or "GB").strip().upper()[:2]
        return _COUNTRY_CODE_TO_MARKET.get(code, "gbp")

    @staticmethod
    def market_for_org(db: Session, org: Organisation | None) -> str:
        code = CountryVatService.resolve_org_country_code(db, org)
        return PricingMarketService.market_for_country_code(code)

    @staticmethod
    def resolve_market_param(db: Session, *, org: Organisation | None, market: str | None) -> str:
        raw = str(market or "").strip().lower()
        if raw in {"", "auto", "org"}:
            return PricingMarketService.market_for_org(db, org)
        if raw in MARKETS:
            return raw
        return PricingMarketService.market_for_org(db, org)

    @staticmethod
    def market_label(market: str) -> str:
        labels = {"gbp": "United Kingdom (GBP)", "cad": "Canada (CAD)", "aud": "Australia (AUD)", "usd": "United States (USD)"}
        return labels.get(str(market or "gbp").lower(), "United Kingdom (GBP)")

    @staticmethod
    def currency_symbol(market: str) -> str:
        return MARKET_SYMBOLS.get(str(market or "gbp").lower(), "£")

    @staticmethod
    def currency_code(market: str) -> str:
        codes = {"gbp": "GBP", "cad": "CAD", "aud": "AUD", "usd": "USD"}
        return codes.get(str(market or "gbp").lower(), "GBP")

    @staticmethod
    def charge_pence_for_order(db: Session, *, gbp_pence: int, org: Organisation | None) -> tuple[int, str, str]:
        from app.services.voxbulk_pricing_service import VoxbulkPricingService

        market = PricingMarketService.market_for_org(db, org)
        settings = VoxbulkPricingService.get_settings(db)
        base = max(0, int(gbp_pence or 0))
        if market == "gbp":
            charge = base
        else:
            charge = int(VoxbulkPricingService.convert_pence(base, market, settings) or base)
        return charge, PricingMarketService.currency_code(market), market

    @staticmethod
    def attach_order_quote_display(db: Session, payload: dict[str, Any], org: Organisation | None) -> dict[str, Any]:
        from app.services.voxbulk_pricing_service import VoxbulkPricingService

        market = PricingMarketService.market_for_org(db, org)
        settings = VoxbulkPricingService.get_settings(db)
        pence = int(payload.get("quote_total_pence") or 0)
        payload["pricing_market"] = market
        payload["quote_total_display"] = VoxbulkPricingService.money_display(pence, market, settings)
        payload["currency_symbol"] = PricingMarketService.currency_symbol(market)
        return payload
