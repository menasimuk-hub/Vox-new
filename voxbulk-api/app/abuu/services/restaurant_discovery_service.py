"""Rank nearby restaurants by distance, availability, and menu match."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerProfile, Restaurant
from app.abuu.services.kb_service import resolve_settings
from app.abuu.services.location_service import find_nearest_restaurants
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.preference_service import category_keywords, match_food_categories
from app.abuu.services.reply_service import localized_name


@dataclass(frozen=True)
class RankedRestaurant:
    restaurant: Restaurant
    distance_km: float
    match_score: int
    is_open: bool


def _menu_match_score(db: Session, restaurant_id: str, categories: list[str]) -> int:
    if not categories:
        return 0
    items = AbuuOrderDraftService.list_menu_items(db, restaurant_id, categories=categories, limit=20)
    return len(items)


def rank_restaurants(
    db: Session,
    *,
    lat: float | None,
    lng: float | None,
    categories: list[str] | None = None,
    limit: int = 5,
) -> list[RankedRestaurant]:
    categories = categories or []
    if lat is not None and lng is not None:
        nearest = find_nearest_restaurants(db, lat=lat, lng=lng, limit=20)
        candidates = [row.restaurant for row in nearest]
        distance_map = {row.restaurant.id: row.distance_km for row in nearest}
    else:
        from sqlalchemy import select

        candidates = list(
            db.execute(
                select(Restaurant).where(
                    Restaurant.is_deleted.is_(False),
                    Restaurant.is_available.is_(True),
                    Restaurant.status == "active",
                )
            ).scalars().all()
        )
        distance_map = {r.id: 999.0 for r in candidates}

    ranked: list[RankedRestaurant] = []
    for restaurant in candidates:
        if not restaurant.is_available or restaurant.status != "active":
            continue
        settings = resolve_settings(db, restaurant_id=restaurant.id)
        match = _menu_match_score(db, restaurant.id, categories) if categories else 1
        if categories and match == 0:
            continue
        ranked.append(
            RankedRestaurant(
                restaurant=restaurant,
                distance_km=float(distance_map.get(restaurant.id, 999.0)),
                match_score=match,
                is_open=restaurant.is_available,
            )
        )

    ranked.sort(key=lambda row: (0 if row.is_open else 1, row.distance_km, -row.match_score))
    return ranked[: max(3 if categories else 1, limit)]


def detect_categories_from_text(text: str) -> list[str]:
    return match_food_categories(text)


def format_restaurant_list(
    ranked: list[RankedRestaurant],
    *,
    lang: str,
    page: int = 0,
    page_size: int = 3,
) -> str:
    if not ranked:
        if lang == "en":
            return "No restaurants are available right now."
        return "لا توجد مطاعم متاحة حالياً."

    start = page * page_size
    page_rows = ranked[start : start + page_size]
    lines: list[str] = []
    if lang == "en":
        lines.append("Nearby restaurants:")
    else:
        lines.append("المطاعم القريبة:")
    for idx, row in enumerate(page_rows, start=start + 1):
        name = localized_name(row.restaurant, lang)
        status = "open" if row.is_open else "closed"
        if lang == "en":
            lines.append(f"{idx}. {name} — {row.distance_km:.1f} km ({status})")
        else:
            st = "مفتوح" if row.is_open else "مغلق"
            lines.append(f"{idx}. {name} — {row.distance_km:.1f} كم ({st})")
    if start + page_size < len(ranked):
        if lang == "en":
            lines.append("Say **more** for more restaurants, or reply with a restaurant name.")
        else:
            lines.append("اكتب **المزيد** لمطاعم أخرى، أو اسم المطعم.")
    else:
        if lang == "en":
            lines.append("Reply with a restaurant name or tell me what you'd like to eat.")
        else:
            lines.append("أرسل اسم المطعم أو ما تحب أن تأكله.")
    return "\n".join(lines)


def pick_restaurant_by_ref(ranked: list[RankedRestaurant], ref: str) -> Restaurant | None:
    ref = str(ref or "").strip().lower()
    if ref.isdigit():
        idx = int(ref) - 1
        if 0 <= idx < len(ranked):
            return ranked[idx].restaurant
    for row in ranked:
        name_en = row.restaurant.name_en.lower()
        name_ar = row.restaurant.name_ar.lower()
        if ref in name_en or ref in name_ar or name_en in ref or name_ar in ref:
            return row.restaurant
    return None


def specialty_hint(db: Session, restaurant_id: str, categories: list[str], lang: str) -> str:
    if not categories:
        return ""
    items = AbuuOrderDraftService.list_menu_items(db, restaurant_id, categories=categories, limit=2)
    if not items:
        return ""
    names = [localized_name(item, lang) for item in items[:2]]
    joined = ", ".join(names)
    if lang == "en":
        return f"Try: {joined}"
    return f"جرّب: {joined}"
