"""Menu knowledge base with fuzzy search."""

from __future__ import annotations

import logging
import time
from typing import Any

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerProfile, RestaurantMenuCategory, RestaurantMenuItem
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import localized_name
from app.abuu.voice_interpretation.normalize import normalize_ar as _normalize_ar
from app.abuu.voice_interpretation.normalize import normalize_query as _normalize_query

logger = logging.getLogger(__name__)

_MENU_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL_SECONDS = 300


def invalidate_menu_cache(restaurant_id: str | None = None) -> None:
    if restaurant_id:
        _MENU_CACHE.pop(restaurant_id, None)
    else:
        _MENU_CACHE.clear()


def _category_map(db: Session, restaurant_id: str) -> dict[str, RestaurantMenuCategory]:
    rows = db.execute(
        select(RestaurantMenuCategory).where(
            RestaurantMenuCategory.restaurant_id == restaurant_id,
            RestaurantMenuCategory.is_deleted.is_(False),
        )
    ).scalars().all()
    return {row.id: row for row in rows}


def get_menu(
    db: Session,
    restaurant_id: str,
    *,
    customer: CustomerProfile | None = None,
) -> list[dict[str, Any]]:
    now = time.time()
    cached = _MENU_CACHE.get(restaurant_id)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return list(cached[1])

    categories = _category_map(db, restaurant_id)
    items = AbuuOrderDraftService.list_menu_items(db, restaurant_id, limit=500, customer=customer)
    menu: list[dict[str, Any]] = []
    for item in items:
        cat = categories.get(item.category_id)
        category_name = ""
        if cat is not None:
            category_name = cat.name_en or cat.name_ar or ""
        menu.append(
            {
                "id": item.id,
                "name_en": item.name_en,
                "name_ar": item.name_ar,
                "description_en": item.description_en or "",
                "description_ar": item.description_ar or "",
                "price": item.price_agorot / 100,
                "price_agorot": item.price_agorot,
                "category": category_name,
                "item_type": item.item_type,
            }
        )
    _MENU_CACHE[restaurant_id] = (now, menu)
    return menu


def _menu_query_from_text(query: str, language: str, *, limit: int):
    from app.abuu.menu_intelligence.arabic_lexicon import expand_food_categories
    from app.abuu.menu_intelligence.query import MenuQuery
    from app.abuu.services.preference_service import match_food_categories

    normalized = _normalize_query(query, language)
    categories = match_food_categories(normalized)
    for extra in expand_food_categories(normalized):
        if extra not in categories:
            categories.append(extra)
    mq = MenuQuery.from_categories(categories or None, limit=limit)
    if "chicken" in normalized or "دجاج" in normalized:
        mq.protein_tags.append("chicken")
    if "fish" in normalized or "سمك" in normalized:
        mq.protein_tags.append("fish")
    if "beef" in normalized or "meat" in normalized or "لحم" in normalized:
        mq.protein_tags.append("beef")
    return mq


def search_menu(
    db: Session,
    restaurant_id: str,
    query: str,
    language: str,
    *,
    customer: CustomerProfile | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    from app.core.config import get_settings

    if get_settings().abuu_menu_intelligence_enabled:
        from app.abuu.menu_intelligence.search_service import MenuSearchService

        mq = _menu_query_from_text(query, language, limit=limit)
        items = MenuSearchService.search(db, restaurant_id, mq, customer=customer)
        categories = _category_map(db, restaurant_id)
        results: list[dict[str, Any]] = []
        for item in items:
            cat = categories.get(item.category_id)
            category_name = ""
            if cat is not None:
                category_name = cat.name_en or cat.name_ar or ""
            results.append(
                {
                    "id": item.id,
                    "name_en": item.name_en,
                    "name_ar": item.name_ar,
                    "description_en": item.description_en or "",
                    "description_ar": item.description_ar or "",
                    "price": item.price_agorot / 100,
                    "price_agorot": item.price_agorot,
                    "category": category_name,
                    "item_type": item.item_type,
                }
            )
        if results:
            return results

    menu = get_menu(db, restaurant_id, customer=customer)
    if not menu:
        return []
    normalized_query = _normalize_query(query, language)
    if not normalized_query:
        return menu[:limit]

    choices: dict[str, dict[str, Any]] = {}
    for row in menu:
        label = localized_name(
            type("Row", (), {"name_en": row["name_en"], "name_ar": row["name_ar"]})(),
            language,
        )
        haystack = " ".join(
            [
                row["name_en"],
                row["name_ar"],
                row.get("category") or "",
                row.get("item_type") or "",
                row.get("description_en") or "",
                row.get("description_ar") or "",
            ]
        )
        key = f"{row['id']}:{label}"
        choices[key] = {**row, "_search_text": _normalize_query(haystack, language)}

    scored = process.extract(
        normalized_query,
        {k: v["_search_text"] for k, v in choices.items()},
        scorer=fuzz.WRatio,
        limit=max(limit, 5),
    )
    results: list[dict[str, Any]] = []
    for _match, score, key in scored:
        if score < 45:
            continue
        row = dict(choices[key])
        row.pop("_search_text", None)
        row["match_score"] = score
        results.append(row)
        if len(results) >= limit:
            break
    return results
