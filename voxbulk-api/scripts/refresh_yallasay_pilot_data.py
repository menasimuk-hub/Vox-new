#!/usr/bin/env python3
"""Refresh all 5 Yallasay pilot restaurants: menus, recipe/allergen tags, offers, KB disclaimers.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python scripts/refresh_yallasay_pilot_data.py
  python scripts/refresh_yallasay_pilot_data.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from app.abuu.models.entities import RestaurantMenuItem, RestaurantPromoOffer
from app.abuu.services.agent_settings_seed import refresh_pilot_allergen_disclaimers, seed_agent_settings
from app.abuu.services.seed_service import AbuuSeedService
from app.abuu.services.yallasay_menu_catalog import YALLASAY_PILOT_RESTAURANT_IDS
from app.abuu.services.yallasay_menu_seed_service import YallasayMenuSeedService
from app.abuu.services.yallasay_wa_snapshot_service import YallasayWaSnapshotService
from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations


def _tag_coverage(db) -> dict[str, int]:
    rows = db.execute(
        select(
            func.count(RestaurantMenuItem.id),
            func.sum(RestaurantMenuItem.recipe_tags_json.isnot(None)),
            func.sum(RestaurantMenuItem.allergen_tags_json.isnot(None)),
            func.sum(RestaurantMenuItem.classification_status == "classified"),
        ).where(RestaurantMenuItem.is_deleted.is_(False))
    ).one()
    total, recipe, allergen, classified = rows
    return {
        "menu_items": int(total or 0),
        "with_recipe_tags": int(recipe or 0),
        "with_allergen_tags": int(allergen or 0),
        "classified": int(classified or 0),
    }


def _offer_counts(db) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rid in YALLASAY_PILOT_RESTAURANT_IDS:
        n = db.execute(
            select(func.count())
            .select_from(RestaurantPromoOffer)
            .where(
                RestaurantPromoOffer.restaurant_id == rid,
                RestaurantPromoOffer.is_deleted.is_(False),
                RestaurantPromoOffer.is_active.is_(True),
            )
        ).scalar_one()
        counts[rid] = int(n or 0)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh Yallasay pilot menus, tags, offers, allergen KB")
    parser.add_argument("--dry-run", action="store_true", help="Preview only — no DB writes")
    args = parser.parse_args()

    run_abuu_migrations()

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.ensure_pilot_restaurants(db)
        YallasayWaSnapshotService.ensure_gaza_market_agent(db)
        seed_agent_settings(db)
        if args.dry_run:
            db.rollback()
            print("dry-run: would refresh pilot-five menus, tags, offers, snapshots")
            return 0

        results = YallasayMenuSeedService.seed_pilot_five(db, with_offers=True)
        refresh_pilot_allergen_disclaimers(db)

        for row in results:
            if not row.get("error"):
                YallasayWaSnapshotService.rebuild_restaurant(db, row["restaurant_id"])
        YallasayWaSnapshotService.rebuild_marketplace(db)
        db.commit()

        coverage = _tag_coverage(db)
        offers = _offer_counts(db)

    print("Pilot refresh complete.")
    for row in results:
        if row.get("error"):
            print(f"  {row['restaurant_id']}: ERROR — {row['error']}")
        else:
            print(
                f"  {row['restaurant_id']}: categories={row['categories']} "
                f"new_items={row['items']} offers_touched={row['offers']}"
            )
    print(f"Tag coverage: {json.dumps(coverage, ensure_ascii=False)}")
    print(f"Active offers per restaurant: {json.dumps(offers, ensure_ascii=False)}")
    return 1 if any(r.get("error") for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
