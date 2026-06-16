#!/usr/bin/env python3
"""Enrich Abuu menu items with structured allergen, recipe, and dietary tags."""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select

from app.abuu.menu_intelligence.enrich_rules import apply_inferred_tags, infer_tags_for_item
from app.abuu.models.entities import Restaurant, RestaurantMenuCategory, RestaurantMenuItem
from app.abuu.services.yallasay_menu_catalog import YALLASAY_PILOT_RESTAURANT_IDS, menu_for_profile, profile_for_restaurant
from app.abuu.services.yallasay_menu_seed_service import _item_id
from app.core.abuu_database import get_abuu_sessionmaker


def enrich_restaurant(db, restaurant_id: str, *, apply: bool, force: bool) -> dict[str, int]:
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise ValueError(f"Restaurant not found: {restaurant_id}")

    profile = profile_for_restaurant(restaurant_id)
    catalog = menu_for_profile(profile)
    spec_by_id: dict[str, tuple[str, dict]] = {}
    for cat in catalog:
        for item in cat.get("items") or []:
            spec_by_id[_item_id(restaurant_id, item["key"])] = (cat["key"], item)

    cat_ids = [
        c.id
        for c in db.execute(
            select(RestaurantMenuCategory).where(
                RestaurantMenuCategory.restaurant_id == restaurant_id,
                RestaurantMenuCategory.is_deleted.is_(False),
            )
        ).scalars().all()
    ]
    if not cat_ids:
        return {"items_seen": 0, "items_updated": 0}

    rows = list(
        db.execute(
            select(RestaurantMenuItem).where(
                RestaurantMenuItem.category_id.in_(cat_ids),
                RestaurantMenuItem.is_deleted.is_(False),
            )
        ).scalars().all()
    )

    updated = 0
    for row in rows:
        cat_key, spec = spec_by_id.get(
            row.id,
            (
                "general",
                {
                    "name_en": row.name_en,
                    "name_ar": row.name_ar,
                    "item_type": row.item_type,
                    "description_en": row.description_en,
                    "description_ar": row.description_ar,
                },
            ),
        )
        inferred = infer_tags_for_item(cat_key=cat_key, item_spec=spec, profile=profile)
        if apply_inferred_tags(row, inferred, force=force):
            updated += 1
            if apply:
                db.add(row)

    if apply and updated:
        db.commit()
    return {"items_seen": len(rows), "items_updated": updated}


def audit_unclassified(db) -> list[dict]:
    rows = db.execute(
        select(RestaurantMenuItem).where(
            RestaurantMenuItem.is_deleted.is_(False),
            RestaurantMenuItem.classification_status.in_(("unclassified", None)),
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "name_en": r.name_en,
            "name_ar": r.name_ar,
            "item_type": r.item_type,
            "classification_status": r.classification_status,
        }
        for r in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich Abuu menu tags (allergen, recipe, dietary)")
    parser.add_argument("--restaurant-id", action="append", dest="restaurant_ids")
    parser.add_argument("--pilot-five", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Write changes to DB")
    parser.add_argument("--dry-run", action="store_true", help="Same as default without --apply")
    parser.add_argument("--force", action="store_true", help="Overwrite existing tag fields")
    parser.add_argument("--audit-unclassified", action="store_true")
    args = parser.parse_args()

    with get_abuu_sessionmaker()() as db:
        if args.audit_unclassified:
            report = audit_unclassified(db)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0

        ids = list(args.restaurant_ids or [])
        if args.pilot_five:
            ids.extend(YALLASAY_PILOT_RESTAURANT_IDS)
        if not ids:
            parser.error("Specify --restaurant-id or --pilot-five")

        apply = bool(args.apply) and not args.dry_run
        totals = {"items_seen": 0, "items_updated": 0}
        for rid in dict.fromkeys(ids):
            result = enrich_restaurant(db, rid, apply=apply, force=args.force)
            print(f"{rid}: {result}")
            totals["items_seen"] += result["items_seen"]
            totals["items_updated"] += result["items_updated"]
        print(f"done apply={apply} totals={totals}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
