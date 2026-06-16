"""Pre-fetch restaurant lists and offers before the LLM loop."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.market.registry import get_market_agent, marketplace_scope, restaurant_scope
from app.abuu.services.location_service import get_default_address, ignore_delivery_distance
from app.abuu.services.offer_service import (
    AbuuOfferService,
    best_offer_match,
    categories_from_offer_query,
    format_offer_match_hint,
    format_offers_list,
    rank_offers_by_query,
)
from app.abuu.services.restaurant_discovery_service import format_restaurant_list, rank_restaurants
from app.abuu.services.yallasay_wa_snapshot_service import YallasayWaSnapshotService
from app.core.config import get_settings


def restaurant_list_page_size() -> int:
    return 15 if ignore_delivery_distance() else 5


def _pilot_ids(db: Session) -> tuple[str, ...] | None:
    if not get_settings().abuu_pilot_only:
        return None
    return get_market_agent(db).pilot_restaurant_ids


def prefetch_restaurant_list(db: Session, session: AgentSession, *, customer_id: str) -> str:
    lang = session.language or "ar"
    market = get_market_agent(db)
    cached = YallasayWaSnapshotService.get_body(
        db,
        scope=marketplace_scope(market.id),
        kind="restaurant_list",
        lang=lang if lang in {"ar", "en"} else "ar",
    )
    if cached:
        session.context["prefetched_restaurant_list"] = cached
        payload_row = YallasayWaSnapshotService.get(
            db,
            scope=marketplace_scope(market.id),
            kind="restaurant_list",
            lang=lang if lang in {"ar", "en"} else "ar",
        )
        if payload_row and payload_row.payload_json:
            import json

            try:
                data = json.loads(payload_row.payload_json)
                session.context["ranked_restaurants"] = data.get("restaurants") or []
            except json.JSONDecodeError:
                pass
        return cached

    addr = get_default_address(db, customer_id)
    lat = addr.latitude if addr else None
    lng = addr.longitude if addr else None
    ranked = rank_restaurants(
        db,
        lat=lat,
        lng=lng,
        categories=None,
        limit=15,
        restaurant_ids=_pilot_ids(db),
    )
    session.context["ranked_restaurants"] = [
        {"id": r.restaurant.id, "name_en": r.restaurant.name_en, "name_ar": r.restaurant.name_ar}
        for r in ranked
    ]
    listing = format_restaurant_list(
        ranked,
        lang=lang,
        page=0,
        page_size=restaurant_list_page_size(),
    )
    session.context["prefetched_restaurant_list"] = listing
    return listing


def prefetch_offers(db: Session, session: AgentSession, *, query: str = "") -> str:
    lang = session.language or "ar"
    if session.restaurant_id:
        cached = YallasayWaSnapshotService.get_body(
            db,
            scope=restaurant_scope(session.restaurant_id),
            kind="offers",
            lang=lang if lang in {"ar", "en"} else "ar",
        )
        if cached and not str(query or "").strip():
            session.context["prefetched_offers"] = cached
            return cached

    cleaned_query = str(query or "").strip()
    session.context.pop("matched_offer_id", None)
    session.context.pop("matched_offer_hint", None)

    offers: list = []
    if cleaned_query:
        ranked = rank_offers_by_query(
            db,
            cleaned_query,
            restaurant_id=session.restaurant_id,
            limit=15,
        )
        if ranked:
            offers = [row.offer for row in ranked]
            best = ranked[0]
            if best.score >= 5.0:
                session.context["matched_offer_id"] = best.offer.id
                session.context["matched_offer_hint"] = format_offer_match_hint(db, best, lang=lang)

    if not offers:
        categories = categories_from_offer_query(cleaned_query) if cleaned_query else None
        offers = AbuuOfferService.list_active(
            db,
            restaurant_id=session.restaurant_id,
            categories=categories,
            limit=15,
        )
        if cleaned_query and not session.context.get("matched_offer_id"):
            fallback = best_offer_match(
                db,
                cleaned_query,
                restaurant_id=session.restaurant_id,
                lang=lang,
            )
            if fallback is not None:
                session.context["matched_offer_id"] = fallback.offer.id
                session.context["matched_offer_hint"] = format_offer_match_hint(db, fallback, lang=lang)

    listing = format_offers_list(db, offers, lang=lang)
    hint = session.context.get("matched_offer_hint")
    if isinstance(hint, str) and hint.strip():
        listing = f"{listing}\n{hint}"
    session.context["prefetched_offers"] = listing
    return listing
