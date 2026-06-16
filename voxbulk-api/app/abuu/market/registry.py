"""Market-scoped food agents (Gaza Agent, future cities)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.abuu.models.entities import AbuuMarketAgent
from app.abuu.services.yallasay_menu_catalog import YALLASAY_PILOT_RESTAURANT_IDS
from app.core.config import get_settings

DEFAULT_MARKET_ID = "ps-gaza"

_GAZA_DIALECT = (
    "Levantine Palestinian Arabic — Gaza style. Warm, natural, like a local restaurant waiter. "
    "Short WhatsApp replies (2–3 lines). Ordering food only."
)


@dataclass(frozen=True)
class MarketAgentConfig:
    id: str
    country_code: str
    city_slug: str
    display_name_en: str
    display_name_ar: str
    dialect_prompt: str
    llm_provider: str
    llm_model: str
    pilot_restaurant_ids: tuple[str, ...]


def _default_gaza() -> MarketAgentConfig:
    settings = get_settings()
    return MarketAgentConfig(
        id=DEFAULT_MARKET_ID,
        country_code="ps",
        city_slug="gaza",
        display_name_en="Gaza Agent",
        display_name_ar="وكيل غزة",
        dialect_prompt=_GAZA_DIALECT,
        llm_provider="deepseek",
        llm_model=settings.abuu_agent_model or "deepseek-chat",
        pilot_restaurant_ids=YALLASAY_PILOT_RESTAURANT_IDS,
    )


def active_market_id() -> str:
    settings = get_settings()
    market = (settings.abuu_market_agent or "").strip()
    if market:
        return market
    country = (settings.abuu_agent_country or "ps").strip().lower()
    city = (settings.abuu_agent_city or "gaza").strip().lower()
    return f"{country}-{city}"


def get_market_agent(db: Session | None = None) -> MarketAgentConfig:
    market_id = active_market_id()
    if db is not None:
        row = db.get(AbuuMarketAgent, market_id)
        if row is not None and row.is_active:
            ids_raw = row.pilot_restaurant_ids_json or "[]"
            try:
                ids = tuple(json.loads(ids_raw))
            except json.JSONDecodeError:
                ids = YALLASAY_PILOT_RESTAURANT_IDS
            if not ids:
                ids = YALLASAY_PILOT_RESTAURANT_IDS
            return MarketAgentConfig(
                id=row.id,
                country_code=row.country_code,
                city_slug=row.city_slug,
                display_name_en=row.display_name_en,
                display_name_ar=row.display_name_ar,
                dialect_prompt=row.dialect_prompt or _GAZA_DIALECT,
                llm_provider=row.llm_provider or "deepseek",
                llm_model=row.llm_model or "deepseek-chat",
                pilot_restaurant_ids=ids,
            )
    if market_id == DEFAULT_MARKET_ID:
        return _default_gaza()
    return _default_gaza()


def marketplace_scope(market_id: str | None = None) -> str:
    return f"marketplace:{market_id or active_market_id()}"


def restaurant_scope(restaurant_id: str) -> str:
    return f"restaurant:{restaurant_id}"
