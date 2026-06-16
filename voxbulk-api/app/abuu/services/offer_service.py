"""Restaurant promo offers — CRUD and agent formatting."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import Restaurant, RestaurantMenuItem, RestaurantPromoOffer
from app.abuu.services.preference_service import match_food_categories
from app.abuu.services.reply_service import format_shekel, localized_name


def _parse_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def offer_to_dict(row: RestaurantPromoOffer) -> dict[str, Any]:
    return {
        "id": row.id,
        "restaurant_id": row.restaurant_id,
        "title_en": row.title_en,
        "title_ar": row.title_ar,
        "description_en": row.description_en,
        "description_ar": row.description_ar,
        "offer_price_agorot": row.offer_price_agorot,
        "original_price_agorot": row.original_price_agorot,
        "items": _parse_json(row.items_json, []),
        "tags": _parse_json(row.tags_json, []),
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class AbuuOfferService:
    @staticmethod
    def list_for_restaurant(db: Session, restaurant_id: str, *, active_only: bool = True) -> list[RestaurantPromoOffer]:
        stmt = select(RestaurantPromoOffer).where(
            RestaurantPromoOffer.restaurant_id == restaurant_id,
            RestaurantPromoOffer.is_deleted.is_(False),
        )
        if active_only:
            stmt = stmt.where(RestaurantPromoOffer.is_active.is_(True))
        return list(db.execute(stmt.order_by(RestaurantPromoOffer.created_at.desc())).scalars().all())

    @staticmethod
    def list_active(
        db: Session,
        *,
        restaurant_id: str | None = None,
        categories: list[str] | None = None,
        limit: int = 20,
    ) -> list[RestaurantPromoOffer]:
        stmt = select(RestaurantPromoOffer).where(
            RestaurantPromoOffer.is_deleted.is_(False),
            RestaurantPromoOffer.is_active.is_(True),
        )
        if restaurant_id:
            stmt = stmt.where(RestaurantPromoOffer.restaurant_id == restaurant_id)
        rows = list(db.execute(stmt.order_by(RestaurantPromoOffer.created_at.desc()).limit(limit)).scalars().all())
        if not categories:
            return rows
        filtered: list[RestaurantPromoOffer] = []
        for row in rows:
            tags = [str(t).lower() for t in _parse_json(row.tags_json, [])]
            if any(cat in tags for cat in categories):
                filtered.append(row)
                continue
            if row.restaurant_id:
                restaurant = db.get(Restaurant, row.restaurant_id)
                if restaurant and any(cat in (restaurant.name_en or "").lower() or cat in (restaurant.name_ar or "") for cat in categories):
                    filtered.append(row)
        return filtered

    @staticmethod
    def create(
        db: Session,
        *,
        restaurant_id: str,
        title_en: str,
        title_ar: str,
        offer_price_agorot: int,
        original_price_agorot: int,
        items: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        description_en: str | None = None,
        description_ar: str | None = None,
        is_active: bool = True,
    ) -> RestaurantPromoOffer:
        row = RestaurantPromoOffer(
            restaurant_id=restaurant_id,
            title_en=title_en.strip(),
            title_ar=title_ar.strip(),
            description_en=description_en,
            description_ar=description_ar,
            offer_price_agorot=max(0, int(offer_price_agorot)),
            original_price_agorot=max(0, int(original_price_agorot)),
            items_json=json.dumps(items or [], ensure_ascii=False),
            tags_json=json.dumps(tags or [], ensure_ascii=False),
            is_active=is_active,
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def patch(db: Session, row: RestaurantPromoOffer, payload: dict[str, Any]) -> RestaurantPromoOffer:
        for field in ("title_en", "title_ar", "description_en", "description_ar", "is_active"):
            if field in payload:
                setattr(row, field, payload[field])
        for field in ("offer_price_agorot", "original_price_agorot"):
            if field in payload:
                setattr(row, field, max(0, int(payload[field])))
        if "items" in payload:
            row.items_json = json.dumps(payload["items"] or [], ensure_ascii=False)
        if "tags" in payload:
            row.tags_json = json.dumps(payload["tags"] or [], ensure_ascii=False)
        db.add(row)
        return row

    @staticmethod
    def delete(db: Session, row: RestaurantPromoOffer) -> None:
        row.is_deleted = True
        row.is_active = False
        db.add(row)


def format_offers_list(
    db: Session,
    offers: list[RestaurantPromoOffer],
    *,
    lang: str,
) -> str:
    if not offers:
        if lang == "en":
            return "No active offers right now."
        return "لا توجد عروض نشطة حالياً."

    lines: list[str] = []
    if lang == "en":
        lines.append("Active offers:")
    else:
        lines.append("العروض النشطة:")
    for idx, offer in enumerate(offers, start=1):
        restaurant = db.get(Restaurant, offer.restaurant_id)
        rest_name = localized_name(restaurant, lang) if restaurant else offer.restaurant_id
        title = offer.title_ar if lang == "ar" else offer.title_en
        title = title or offer.title_en or offer.title_ar
        offer_price = format_shekel(offer.offer_price_agorot)
        original = format_shekel(offer.original_price_agorot)
        tags = _parse_json(offer.tags_json, [])
        tag_text = ", ".join(str(t) for t in tags) if tags else ""
        if lang == "en":
            line = f"{idx}. {title} @ {rest_name} — {offer_price}"
            if offer.original_price_agorot > offer.offer_price_agorot:
                line += f" (was {original})"
            if tag_text:
                line += f" ({tag_text})"
        else:
            line = f"{idx}. {title} — {rest_name} — {offer_price}"
            if offer.original_price_agorot > offer.offer_price_agorot:
                line += f" (بدل {original})"
            if tag_text:
                line += f" ({tag_text})"
        lines.append(line)
    if lang == "en":
        lines.append("Reply with an offer number or restaurant name to order from that offer.")
    else:
        lines.append("أرسل رقم العرض أو اسم المطعم للطلب من العرض.")
    return "\n".join(lines)


def categories_from_offer_query(query: str) -> list[str]:
    return match_food_categories(str(query or "").strip())
