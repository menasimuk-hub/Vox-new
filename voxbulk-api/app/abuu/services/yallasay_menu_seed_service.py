"""Upsert full Yallasay menu + promo offers for one or all restaurants."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.menu_intelligence.enrich_rules import apply_inferred_tags, infer_tags_for_item
from app.abuu.models.entities import Restaurant, RestaurantMenuCategory, RestaurantMenuItem, RestaurantPromoOffer
from app.abuu.services.yallasay_menu_catalog import (
    YALLASAY_PILOT_RESTAURANT_IDS,
    menu_for_profile,
    offers_for_profile,
    profile_for_restaurant,
)

# UUID namespace for deterministic 36-char ids (abuu id columns are String(36)).
_YALLASAY_NS = uuid.UUID("a3b8c2e1-7f4d-4e9a-b2c1-8d6e5f4a3b2c")
_MAX_ID_LEN = 36


def _stable_id(kind: str, restaurant_id: str, key: str) -> str:
    value = str(uuid.uuid5(_YALLASAY_NS, f"yallasay:{kind}:{restaurant_id}:{key}"))
    if len(value) > _MAX_ID_LEN:
        raise ValueError(f"Generated id too long: {value}")
    return value


def _cat_id(restaurant_id: str, cat_key: str) -> str:
    return _stable_id("cat", restaurant_id, cat_key)


def _item_id(restaurant_id: str, item_key: str) -> str:
    return _stable_id("item", restaurant_id, item_key)


def _offer_id(restaurant_id: str, offer_key: str) -> str:
    return _stable_id("offer", restaurant_id, offer_key)


class YallasayMenuSeedService:
    @staticmethod
    def seed_restaurant(
        db: Session,
        restaurant_id: str,
        *,
        with_offers: bool = True,
    ) -> dict[str, int]:
        restaurant = db.get(Restaurant, restaurant_id)
        if restaurant is None or restaurant.is_deleted:
            raise ValueError(f"Restaurant not found: {restaurant_id}")

        now = datetime.utcnow()
        categories_upserted = 0
        items_upserted = 0
        item_price_map: dict[str, int] = {}

        profile = profile_for_restaurant(restaurant_id)
        menu_catalog = menu_for_profile(profile)
        offer_templates = offers_for_profile(profile)

        for cat_idx, cat_spec in enumerate(menu_catalog, start=1):
            cat_id = _cat_id(restaurant_id, cat_spec["key"])
            category = db.get(RestaurantMenuCategory, cat_id)
            if category is None:
                category = RestaurantMenuCategory(
                    id=cat_id,
                    restaurant_id=restaurant_id,
                    name_en=cat_spec["name_en"],
                    name_ar=cat_spec["name_ar"],
                    sort_order=cat_idx * 10,
                    is_available=True,
                    created_at=now,
                    updated_at=now,
                    is_deleted=False,
                )
                db.add(category)
                categories_upserted += 1
            else:
                category.name_en = cat_spec["name_en"]
                category.name_ar = cat_spec["name_ar"]
                category.sort_order = cat_idx * 10
                category.is_available = True
                category.is_deleted = False
                category.deleted_at = None
                category.updated_at = now
                db.add(category)

            for item_spec in cat_spec["items"]:
                iid = _item_id(restaurant_id, item_spec["key"])
                item_price_map[item_spec["key"]] = int(item_spec["price_agorot"])
                inferred = infer_tags_for_item(
                    cat_key=cat_spec["key"],
                    item_spec=item_spec,
                    profile=profile,
                )
                row = db.get(RestaurantMenuItem, iid)
                if row is None:
                    row = RestaurantMenuItem(
                        id=iid,
                        category_id=cat_id,
                        name_en=item_spec["name_en"],
                        name_ar=item_spec["name_ar"],
                        description_en=item_spec.get("description_en"),
                        description_ar=item_spec.get("description_ar"),
                        item_type=inferred["item_type"],
                        price_agorot=int(item_spec["price_agorot"]),
                        is_available=True,
                        created_at=now,
                        updated_at=now,
                        is_deleted=False,
                    )
                    apply_inferred_tags(row, inferred, force=True)
                    db.add(row)
                    items_upserted += 1
                else:
                    row.category_id = cat_id
                    row.name_en = item_spec["name_en"]
                    row.name_ar = item_spec["name_ar"]
                    row.description_en = item_spec.get("description_en")
                    row.description_ar = item_spec.get("description_ar")
                    row.item_type = inferred["item_type"]
                    row.price_agorot = int(item_spec["price_agorot"])
                    row.is_available = True
                    row.is_deleted = False
                    row.deleted_at = None
                    row.updated_at = now
                    apply_inferred_tags(row, inferred, force=False)
                    db.add(row)

        offers_upserted = 0
        if with_offers:
            offers_upserted = YallasayMenuSeedService._seed_offers(
                db,
                restaurant_id=restaurant_id,
                item_price_map=item_price_map,
                offer_templates=offer_templates,
                now=now,
            )

        db.flush()
        return {
            "restaurant_id": restaurant_id,
            "categories": categories_upserted,
            "items": items_upserted,
            "offers": offers_upserted,
        }

    @staticmethod
    def _seed_offers(
        db: Session,
        *,
        restaurant_id: str,
        item_price_map: dict[str, int],
        offer_templates: list[dict[str, Any]],
        now: datetime,
    ) -> int:
        upserted = 0
        for spec in offer_templates:
            offer_items: list[dict[str, Any]] = []
            original_total = 0
            for row in spec["items"]:
                item_key = row["item_key"]
                qty = int(row.get("quantity") or 1)
                menu_item_id = _item_id(restaurant_id, item_key)
                price = item_price_map.get(item_key)
                if price is None:
                    continue
                original_total += price * qty
                offer_items.append({"menu_item_id": menu_item_id, "quantity": qty})

            if not offer_items or original_total <= 0:
                continue

            discount_pct = int(spec.get("discount_pct") or 10)
            offer_price = max(100, int(original_total * (100 - discount_pct) / 100))
            oid = _offer_id(restaurant_id, spec["key"])
            offer = db.get(RestaurantPromoOffer, oid)
            payload = dict(
                restaurant_id=restaurant_id,
                title_en=spec["title_en"],
                title_ar=spec["title_ar"],
                description_en=spec.get("description_en"),
                description_ar=spec.get("description_ar"),
                offer_price_agorot=offer_price,
                original_price_agorot=original_total,
                items_json=json.dumps(offer_items, ensure_ascii=False),
                tags_json=json.dumps(spec.get("tags") or [], ensure_ascii=False),
                is_active=True,
                updated_at=now,
                is_deleted=False,
                deleted_at=None,
            )
            if offer is None:
                offer = RestaurantPromoOffer(id=oid, created_at=now, **payload)
                db.add(offer)
                upserted += 1
            else:
                for key, value in payload.items():
                    setattr(offer, key, value)
                db.add(offer)
        return upserted

    @staticmethod
    def seed_all_active(
        db: Session,
        *,
        with_offers: bool = True,
        restaurant_ids: list[str] | None = None,
    ) -> list[dict[str, int]]:
        if restaurant_ids:
            ids = restaurant_ids
        else:
            ids = list(
                db.execute(
                    select(Restaurant.id).where(
                        Restaurant.is_deleted.is_(False),
                        Restaurant.status == "active",
                    )
                ).scalars()
            )
        results: list[dict[str, int]] = []
        for rid in ids:
            try:
                row = YallasayMenuSeedService.seed_restaurant(db, rid, with_offers=with_offers)
                db.commit()
                results.append(row)
            except Exception as exc:
                db.rollback()
                results.append(
                    {
                        "restaurant_id": rid,
                        "categories": 0,
                        "items": 0,
                        "offers": 0,
                        "error": str(exc),
                    }
                )
        return results

    @staticmethod
    def seed_pilot_five(db: Session, *, with_offers: bool = True) -> list[dict[str, int]]:
        return YallasayMenuSeedService.seed_all_active(
            db,
            with_offers=with_offers,
            restaurant_ids=list(YALLASAY_PILOT_RESTAURANT_IDS),
        )
