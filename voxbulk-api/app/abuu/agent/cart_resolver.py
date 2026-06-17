"""Resolve LLM cart references (menu index, Arabic name, offer title) to DB rows."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerOrder, RestaurantMenuCategory, RestaurantMenuItem, RestaurantPromoOffer
from app.abuu.services.offer_service import AbuuOfferService, rank_offers_by_query
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import localized_name


def _normalize_ref(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _menu_index_lookup(
    db: Session,
    session_context: dict[str, Any],
    ref: str,
) -> RestaurantMenuItem | None:
    raw = str(ref or "").strip()
    if not raw.isdigit():
        return None
    index = int(raw)
    for row in session_context.get("menu_item_index") or []:
        if not isinstance(row, dict):
            continue
        if int(row.get("index") or 0) == index:
            item_id = str(row.get("id") or "").strip()
            if item_id:
                return db.get(RestaurantMenuItem, item_id)
    return None


def _offer_index_lookup(
    db: Session,
    restaurant_id: str,
    ref: str,
) -> RestaurantPromoOffer | None:
    raw = str(ref or "").strip()
    if not raw.isdigit():
        return None
    index = int(raw)
    offers = AbuuOfferService.list_for_restaurant(db, restaurant_id, active_only=True)
    if 1 <= index <= len(offers):
        return offers[index - 1]
    return None


def _offer_by_ref(
    db: Session,
    *,
    restaurant_id: str,
    ref: str,
    session_context: dict[str, Any],
) -> RestaurantPromoOffer | None:
    raw = str(ref or "").strip()
    if not raw:
        return None

    matched_id = str(session_context.get("matched_offer_id") or "").strip()
    if matched_id:
        row = db.get(RestaurantPromoOffer, matched_id)
        if row is not None and not row.is_deleted and row.is_active:
            hint = _normalize_ref(str(session_context.get("matched_offer_hint") or ""))
            needle = _normalize_ref(raw)
            if needle in hint or raw == "1" or needle in _normalize_ref(row.title_ar or ""):
                return row

    by_index = _offer_index_lookup(db, restaurant_id, raw)
    if by_index is not None:
        return by_index

    needle = _normalize_ref(raw)
    offers = AbuuOfferService.list_for_restaurant(db, restaurant_id, active_only=True)
    for offer in offers:
        titles = {_normalize_ref(offer.title_ar or ""), _normalize_ref(offer.title_en or "")}
        if needle in titles or any(needle in title or title in needle for title in titles if title):
            return offer

    ranked = rank_offers_by_query(db, raw, restaurant_id=restaurant_id, limit=1, min_score=5.0)
    if ranked:
        return ranked[0].offer
    return None


def _menu_item_by_name(
    db: Session,
    *,
    restaurant_id: str,
    ref: str,
) -> RestaurantMenuItem | None:
    needle = _normalize_ref(ref)
    if not needle:
        return None
    cat_ids = [
        c
        for c in db.execute(
            select(RestaurantMenuCategory.id).where(
                RestaurantMenuCategory.restaurant_id == restaurant_id,
                RestaurantMenuCategory.is_deleted.is_(False),
            )
        ).scalars().all()
    ]
    if not cat_ids:
        return None
    rows = list(
        db.execute(
            select(RestaurantMenuItem).where(
                RestaurantMenuItem.category_id.in_(cat_ids),
                RestaurantMenuItem.is_deleted.is_(False),
                RestaurantMenuItem.is_available.is_(True),
            )
        ).scalars().all()
    )
    best: RestaurantMenuItem | None = None
    best_len = 0
    for row in rows:
        names = {_normalize_ref(row.name_ar or ""), _normalize_ref(row.name_en or "")}
        for name in names:
            if not name:
                continue
            if needle == name or needle in name or name in needle:
                if len(name) > best_len:
                    best = row
                    best_len = len(name)
    return best


def resolve_cart_add_target(
    db: Session,
    *,
    restaurant_id: str,
    ref: str,
    session_context: dict[str, Any],
    lang: str = "ar",
) -> tuple[str, Any] | None:
    """Return ('menu_item', item) or ('offer', offer) or None."""
    raw = str(ref or "").strip()
    if not raw:
        return None

    if raw.isdigit():
        item = _menu_index_lookup(db, session_context, raw)
        if item is not None:
            return ("menu_item", item)

    item = db.get(RestaurantMenuItem, raw)
    if item is not None and not item.is_deleted:
        return ("menu_item", item)

    offer = _offer_by_ref(db, restaurant_id=restaurant_id, ref=raw, session_context=session_context)
    if offer is not None:
        return ("offer", offer)

    item = _menu_item_by_name(db, restaurant_id=restaurant_id, ref=raw)
    if item is not None:
        return ("menu_item", item)

    return None


def add_offer_lines_to_order(
    db: Session,
    order: CustomerOrder,
    offer: RestaurantPromoOffer,
) -> list[str]:
    added: list[str] = []
    try:
        payload = json.loads(offer.items_json or "[]")
    except json.JSONDecodeError:
        payload = []
    if not isinstance(payload, list):
        return added
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("menu_item_id") or "").strip()
        qty = max(1, int(entry.get("quantity") or 1))
        item = db.get(RestaurantMenuItem, item_id)
        if item is None:
            continue
        AbuuOrderDraftService.add_item(db, order, item, quantity=qty)
        added.append(localized_name(item, "ar") or item.name_en or item_id)
    return added
