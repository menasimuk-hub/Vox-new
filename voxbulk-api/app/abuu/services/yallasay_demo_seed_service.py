"""Deterministic YallaSay demo seed: 7 restaurant + 3 driver portal accounts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.abuu.models.entities import (
    CustomerOrder,
    DeliveryAssignment,
    Driver,
    Restaurant,
    RestaurantMenuCategory,
    RestaurantMenuItem,
)
from app.abuu.services.yallasay_menu_seed_service import YallasayMenuSeedService
from app.core.security import hash_password

DEMO_PASSWORD = "123456"

DEMO_RESTAURANTS: tuple[dict[str, Any], ...] = (
    {
        "id": "abuu-rest-chicken",
        "email": "res1@yallasay.com",
        "name_en": "Sham Chicken",
        "name_ar": "دجاج الشام",
        "phone": "+972501000003",
        "latitude": 31.3520,
        "longitude": 34.3060,
        "address_text": "Gaza — chicken grill",
    },
    {
        "id": "abuu-rest-meat",
        "email": "res2@yallasay.com",
        "name_en": "Abu Hassan Grill",
        "name_ar": "مشاوي أبو حسن",
        "phone": "+972501000002",
        "latitude": 31.3560,
        "longitude": 34.3100,
        "address_text": "Gaza — mixed grill",
    },
    {
        "id": "abuu-rest-fish",
        "email": "res3@yallasay.com",
        "name_en": "Al-Bahr Seafood",
        "name_ar": "مطعم البحر",
        "phone": "+972501000001",
        "latitude": 31.3500,
        "longitude": 34.3040,
        "address_text": "Gaza — seafood",
    },
    {
        "id": "abuu-rest-fastfood",
        "email": "res4@yallasay.com",
        "name_en": "Wajabat Sari'a Fast Food",
        "name_ar": "وجبات سريعة",
        "phone": "+972501000004",
        "latitude": 31.3580,
        "longitude": 34.3120,
        "address_text": "Gaza — fast food counter",
    },
    {
        "id": "abuu-rest-vegetarian",
        "email": "res5@yallasay.com",
        "name_en": "Al-Akhdar Vegetarian",
        "name_ar": "مطعم الأخضر",
        "phone": "+972501000005",
        "latitude": 31.3540,
        "longitude": 34.3080,
        "address_text": "Gaza — vegetarian kitchen",
    },
    {
        "id": "abuu-rest-shawarma",
        "email": "res6@yallasay.com",
        "name_en": "Shawarma Express",
        "name_ar": "شاورما إكسبرس",
        "phone": "+972501000006",
        "latitude": 31.3555,
        "longitude": 34.3095,
        "address_text": "Gaza — shawarma corner",
    },
    {
        "id": "abuu-rest-sweets",
        "email": "res7@yallasay.com",
        "name_en": "Sweet Gaza Bakery",
        "name_ar": "حلويات غزة",
        "phone": "+972501000007",
        "latitude": 31.3530,
        "longitude": 34.3075,
        "address_text": "Gaza — bakery & desserts",
    },
)

DEMO_DRIVERS: tuple[dict[str, Any], ...] = (
    {
        "id": "abuu-driver-demo-01",
        "email": "driver1@yallasay.com",
        "name": "Ahmad Nasser",
        "phone": "+972508010001",
        "vehicle_info": "Scooter — Gaza City",
    },
    {
        "id": "abuu-driver-demo-02",
        "email": "driver2@yallasay.com",
        "name": "Omar Haddad",
        "phone": "+972508010002",
        "vehicle_info": "Motorbike — North Gaza",
    },
    {
        "id": "abuu-driver-demo-03",
        "email": "driver3@yallasay.com",
        "name": "Yousef Barakat",
        "phone": "+972508010003",
        "vehicle_info": "Car — Central Gaza",
    },
)

DEMO_RESTAURANT_IDS: tuple[str, ...] = tuple(row["id"] for row in DEMO_RESTAURANTS)
DEMO_DRIVER_IDS: tuple[str, ...] = tuple(row["id"] for row in DEMO_DRIVERS)


class YallasayDemoSeedService:
    @staticmethod
    def seed_all(db: Session, *, with_offers: bool = True) -> dict[str, Any]:
        from app.abuu.services.seed_service import AbuuSeedService

        AbuuSeedService.ensure_pilot_restaurants(db)
        password_hash = hash_password(DEMO_PASSWORD)
        now = datetime.utcnow()
        restaurants_upserted = 0
        menus: dict[str, dict[str, int]] = {}
        ingredients_updated = 0

        for spec in DEMO_RESTAURANTS:
            row = db.get(Restaurant, spec["id"])
            if row is None:
                row = Restaurant(
                    id=spec["id"],
                    name_en=spec["name_en"],
                    name_ar=spec["name_ar"],
                    status="active",
                    is_available=True,
                    delivery_radius_km=5.0,
                    latitude=spec["latitude"],
                    longitude=spec["longitude"],
                    address_text=spec["address_text"],
                    phone=spec["phone"],
                    login_email=spec["email"],
                    password_hash=password_hash,
                    created_at=now,
                    updated_at=now,
                    is_deleted=False,
                )
                db.add(row)
                restaurants_upserted += 1
            else:
                row.name_en = spec["name_en"]
                row.name_ar = spec["name_ar"]
                row.status = "active"
                row.is_available = True
                row.latitude = spec["latitude"]
                row.longitude = spec["longitude"]
                row.address_text = spec["address_text"]
                row.phone = spec["phone"]
                row.login_email = spec["email"]
                row.password_hash = password_hash
                row.is_deleted = False
                row.deleted_at = None
                row.updated_at = now
                db.add(row)
            db.flush()
            menus[spec["id"]] = YallasayMenuSeedService.seed_restaurant(
                db, spec["id"], with_offers=with_offers
            )

        ingredients_updated = YallasayDemoSeedService._refresh_item_enrichment(db)

        drivers_upserted = 0
        for spec in DEMO_DRIVERS:
            row = db.get(Driver, spec["id"])
            if row is None:
                row = Driver(
                    id=spec["id"],
                    name=spec["name"],
                    phone=spec["phone"],
                    status="active",
                    is_available=True,
                    vehicle_info=spec["vehicle_info"],
                    login_email=spec["email"],
                    password_hash=password_hash,
                    created_at=now,
                    updated_at=now,
                    is_deleted=False,
                )
                db.add(row)
                drivers_upserted += 1
            else:
                row.name = spec["name"]
                row.phone = spec["phone"]
                row.status = "active"
                row.vehicle_info = spec["vehicle_info"]
                row.login_email = spec["email"]
                row.password_hash = password_hash
                row.is_deleted = False
                row.deleted_at = None
                row.updated_at = now
                db.add(row)
            db.flush()

        db.flush()
        from app.abuu.services.yallasay_wa_snapshot_service import YallasayWaSnapshotService
        from app.abuu.services.yallasay_menu_catalog import YALLASAY_PILOT_RESTAURANT_IDS

        YallasayWaSnapshotService.ensure_gaza_market_agent(db)
        for rid in YALLASAY_PILOT_RESTAURANT_IDS:
            YallasayWaSnapshotService.rebuild_restaurant(db, rid)
        YallasayWaSnapshotService.rebuild_marketplace(db)

        return {
            "restaurants_upserted": restaurants_upserted,
            "drivers_upserted": drivers_upserted,
            "menus": menus,
            "ingredients_updated": ingredients_updated,
            "restaurant_accounts": [
                {"id": s["id"], "email": s["email"], "password": DEMO_PASSWORD} for s in DEMO_RESTAURANTS
            ],
            "driver_accounts": [
                {"id": s["id"], "email": s["email"], "password": DEMO_PASSWORD} for s in DEMO_DRIVERS
            ],
        }

    @staticmethod
    def _refresh_item_enrichment(db: Session) -> int:
        from app.abuu.menu_intelligence.enrich_rules import infer_tags_for_item
        from app.abuu.services.yallasay_item_enrichment import apply_yallasay_item_enrichment
        from app.abuu.services.yallasay_menu_catalog import menu_for_profile, profile_for_restaurant
        from app.abuu.services.yallasay_menu_seed_service import _item_id

        updated = 0
        for restaurant_id in DEMO_RESTAURANT_IDS:
            profile = profile_for_restaurant(restaurant_id)
            spec_by_key: dict[str, tuple[str, dict]] = {}
            for cat in menu_for_profile(profile):
                for item_spec in cat.get("items") or []:
                    spec_by_key[item_spec["key"]] = (cat["key"], item_spec)

            category_ids = db.execute(
                select(RestaurantMenuCategory.id).where(
                    RestaurantMenuCategory.restaurant_id == restaurant_id,
                    RestaurantMenuCategory.is_deleted.is_(False),
                )
            ).scalars().all()
            if not category_ids:
                continue
            items = db.execute(
                select(RestaurantMenuItem).where(
                    RestaurantMenuItem.category_id.in_(category_ids),
                    RestaurantMenuItem.is_deleted.is_(False),
                )
            ).scalars().all()
            key_by_id = {_item_id(restaurant_id, key): key for key in spec_by_key}
            for item in items:
                item_key = key_by_id.get(item.id)
                if not item_key:
                    continue
                cat_key, item_spec = spec_by_key[item_key]
                inferred = infer_tags_for_item(cat_key=cat_key, item_spec=item_spec, profile=profile)
                if apply_yallasay_item_enrichment(
                    item,
                    item_key=item_key,
                    item_spec=item_spec,
                    inferred=inferred,
                    force=True,
                ):
                    item.updated_at = datetime.utcnow()
                    db.add(item)
                    updated += 1
        return updated

    @staticmethod
    def count_new_orders(db: Session, restaurant_id: str) -> int:
        return int(
            db.execute(
                select(func.count())
                .select_from(CustomerOrder)
                .where(
                    CustomerOrder.restaurant_id == restaurant_id,
                    CustomerOrder.status.in_(("sent_to_restaurant", "confirmed")),
                )
            ).scalar_one()
            or 0
        )

    @staticmethod
    def driver_assignment_counts(db: Session, driver_id: str) -> dict[str, int]:
        rows = db.execute(
            select(DeliveryAssignment.status, func.count())
            .where(DeliveryAssignment.driver_id == driver_id)
            .group_by(DeliveryAssignment.status)
        ).all()
        by_status = {str(status): int(count) for status, count in rows}
        queued = sum(by_status.get(s, 0) for s in ("assigned", "unassigned"))
        active = sum(by_status.get(s, 0) for s in ("accepted", "on_route"))
        return {
            "queued_orders": queued,
            "active_orders": active,
            "by_status": by_status,
        }
