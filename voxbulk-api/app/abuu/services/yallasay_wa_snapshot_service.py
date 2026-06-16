"""Pre-built WhatsApp text snapshots from local menu DB."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.market.registry import get_market_agent, marketplace_scope, restaurant_scope
from app.abuu.models.entities import AbuuMarketAgent, AbuuWaSnapshot, Restaurant
from app.abuu.services.offer_service import AbuuOfferService, format_offers_list
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import menu_message
from app.abuu.services.restaurant_discovery_service import RankedRestaurant, format_restaurant_list

_SNAPSHOT_NS = uuid.UUID("b8e2f1a3-4c5d-6e7f-8a9b-0c1d2e3f4a5b")


def _snapshot_id(scope: str, kind: str, lang: str) -> str:
    return str(uuid.uuid5(_SNAPSHOT_NS, f"{scope}:{kind}:{lang}"))


class YallasayWaSnapshotService:
    @staticmethod
    def get(db: Session, *, scope: str, kind: str, lang: str) -> AbuuWaSnapshot | None:
        return db.execute(
            select(AbuuWaSnapshot).where(
                AbuuWaSnapshot.scope == scope,
                AbuuWaSnapshot.kind == kind,
                AbuuWaSnapshot.lang == lang,
            )
        ).scalar_one_or_none()

    @staticmethod
    def get_body(db: Session, *, scope: str, kind: str, lang: str) -> str | None:
        row = YallasayWaSnapshotService.get(db, scope=scope, kind=kind, lang=lang)
        return row.body_text if row else None

    @staticmethod
    def upsert(
        db: Session,
        *,
        scope: str,
        kind: str,
        lang: str,
        body_text: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.utcnow()
        sid = _snapshot_id(scope, kind, lang)
        row = db.get(AbuuWaSnapshot, sid)
        payload_json = json.dumps(payload or {}, ensure_ascii=False) if payload else None
        if row is None:
            row = AbuuWaSnapshot(
                id=sid,
                scope=scope,
                kind=kind,
                lang=lang,
                body_text=body_text,
                payload_json=payload_json,
                updated_at=now,
            )
            db.add(row)
        else:
            row.body_text = body_text
            row.payload_json = payload_json
            row.updated_at = now
            db.add(row)

    @staticmethod
    def rebuild_restaurant(db: Session, restaurant_id: str) -> None:
        restaurant = db.get(Restaurant, restaurant_id)
        if restaurant is None or restaurant.is_deleted:
            return
        items = AbuuOrderDraftService.list_menu_items(db, restaurant_id, limit=80)
        indexed = list(enumerate(items, start=1))
        item_index = [
            {
                "index": idx,
                "id": item.id,
                "name_en": item.name_en,
                "name_ar": item.name_ar,
                "price_agorot": item.price_agorot,
            }
            for idx, item in indexed
        ]
        for lang in ("ar", "en"):
            body = menu_message(restaurant, indexed, lang)
            YallasayWaSnapshotService.upsert(
                db,
                scope=restaurant_scope(restaurant_id),
                kind="menu",
                lang=lang,
                body_text=body,
                payload={"items": item_index, "restaurant_id": restaurant_id},
            )
            offers = AbuuOfferService.list_active(db, restaurant_id=restaurant_id, limit=20)
            offers_body = format_offers_list(db, offers, lang=lang)
            YallasayWaSnapshotService.upsert(
                db,
                scope=restaurant_scope(restaurant_id),
                kind="offers",
                lang=lang,
                body_text=offers_body,
                payload={"restaurant_id": restaurant_id, "offer_count": len(offers)},
            )

    @staticmethod
    def rebuild_marketplace(db: Session, market_id: str | None = None) -> None:
        market = get_market_agent(db)
        if market_id and market_id != market.id:
            row = db.get(AbuuMarketAgent, market_id)
            if row is not None and row.is_active:
                try:
                    ids = tuple(json.loads(row.pilot_restaurant_ids_json or "[]"))
                except json.JSONDecodeError:
                    ids = market.pilot_restaurant_ids
                from app.abuu.market.registry import MarketAgentConfig

                market = MarketAgentConfig(
                    id=row.id,
                    country_code=row.country_code,
                    city_slug=row.city_slug,
                    display_name_en=row.display_name_en,
                    display_name_ar=row.display_name_ar,
                    dialect_prompt=row.dialect_prompt or market.dialect_prompt,
                    llm_provider=row.llm_provider or "deepseek",
                    llm_model=row.llm_model or "deepseek-chat",
                    pilot_restaurant_ids=ids or market.pilot_restaurant_ids,
                )
        pilot_ids = list(market.pilot_restaurant_ids)
        ranked: list[RankedRestaurant] = []
        for rid in pilot_ids:
            restaurant = db.get(Restaurant, rid)
            if restaurant is None or restaurant.is_deleted or not restaurant.is_available:
                continue
            ranked.append(
                RankedRestaurant(
                    restaurant=restaurant,
                    distance_km=0.0,
                    match_score=1,
                    is_open=restaurant.is_available,
                )
            )
        scope = marketplace_scope(market.id)
        restaurants_payload = [
            {
                "id": r.restaurant.id,
                "name_en": r.restaurant.name_en,
                "name_ar": r.restaurant.name_ar,
            }
            for r in ranked
        ]
        for lang in ("ar", "en"):
            body = format_restaurant_list(ranked, lang=lang, page=0, page_size=max(15, len(ranked)))
            YallasayWaSnapshotService.upsert(
                db,
                scope=scope,
                kind="restaurant_list",
                lang=lang,
                body_text=body,
                payload={"restaurants": restaurants_payload, "market_id": market.id},
            )

    @staticmethod
    def ensure_gaza_market_agent(db: Session) -> None:
        market = _default_market_row()
        existing = db.get(AbuuMarketAgent, market["id"])
        now = datetime.utcnow()
        if existing is None:
            db.add(AbuuMarketAgent(created_at=now, updated_at=now, **market))
        else:
            for key, value in market.items():
                if key != "id":
                    setattr(existing, key, value)
            existing.updated_at = now
            db.add(existing)


def _default_market_row() -> dict[str, Any]:
    from app.abuu.services.yallasay_menu_catalog import YALLASAY_PILOT_RESTAURANT_IDS

    return {
        "id": "ps-gaza",
        "country_code": "ps",
        "city_slug": "gaza",
        "display_name_en": "Gaza Agent",
        "display_name_ar": "وكيل غزة",
        "dialect_prompt": (
            "Levantine Palestinian Arabic — Gaza style. Warm natural waiter tone. "
            "Ordering food only — not IVR."
        ),
        "llm_provider": "deepseek",
        "llm_model": "deepseek-chat",
        "pilot_restaurant_ids_json": json.dumps(list(YALLASAY_PILOT_RESTAURANT_IDS)),
        "is_active": True,
    }
