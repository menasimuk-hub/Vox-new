"""Pre-fetch restaurant lists and offers before the LLM loop."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.services.location_service import get_default_address, ignore_delivery_distance
from app.abuu.services.offer_service import AbuuOfferService, categories_from_offer_query, format_offers_list
from app.abuu.services.restaurant_discovery_service import format_restaurant_list, rank_restaurants


def restaurant_list_page_size() -> int:
    return 15 if ignore_delivery_distance() else 5


def prefetch_restaurant_list(db: Session, session: AgentSession, *, customer_id: str) -> str:
    addr = get_default_address(db, customer_id)
    lat = addr.latitude if addr else None
    lng = addr.longitude if addr else None
    ranked = rank_restaurants(db, lat=lat, lng=lng, categories=None, limit=15)
    session.context["ranked_restaurants"] = [
        {"id": r.restaurant.id, "name_en": r.restaurant.name_en, "name_ar": r.restaurant.name_ar}
        for r in ranked
    ]
    listing = format_restaurant_list(
        ranked,
        lang=session.language or "ar",
        page=0,
        page_size=restaurant_list_page_size(),
    )
    session.context["prefetched_restaurant_list"] = listing
    return listing


def prefetch_offers(db: Session, session: AgentSession, *, query: str = "") -> str:
    categories = categories_from_offer_query(query) if query else None
    offers = AbuuOfferService.list_active(
        db,
        restaurant_id=session.restaurant_id,
        categories=categories,
        limit=15,
    )
    listing = format_offers_list(db, offers, lang=session.language or "ar")
    session.context["prefetched_offers"] = listing
    return listing
