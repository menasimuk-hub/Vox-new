#!/usr/bin/env python3
"""Seed full Yallasay fast-food menu (burgers, drinks, offers) into Abuu restaurants.

Menu data is stored in MySQL/sqlite Abuu DB:
  - abuu_menu_categories
  - abuu_menu_items
  - abuu_restaurant_offers

Usage (on VPS):
  cd voxbulk-api && source .venv/bin/activate
  python scripts/seed_yallasay_full_menu.py --restaurant-id abuu-rest-fastfood
  python scripts/seed_yallasay_full_menu.py --all
  python scripts/seed_yallasay_full_menu.py --all --no-offers

List restaurants:
  python scripts/seed_yallasay_full_menu.py --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Yallasay full menu + offers")
    parser.add_argument(
        "--restaurant-id",
        action="append",
        dest="restaurant_ids",
        help="Target restaurant id (repeatable). Default fast-food: abuu-rest-fastfood",
    )
    parser.add_argument("--all", action="store_true", help="Seed every active restaurant")
    parser.add_argument("--list", action="store_true", help="List restaurant ids and exit")
    parser.add_argument("--no-offers", action="store_true", help="Skip promo offers")
    args = parser.parse_args()

    from sqlalchemy import select

    from app.abuu.models.entities import Restaurant
    from app.abuu.services.yallasay_menu_seed_service import YallasayMenuSeedService
    from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations

    run_abuu_migrations()

    with get_abuu_sessionmaker()() as db:
        if args.list:
            rows = db.execute(
                select(Restaurant.id, Restaurant.name_en, Restaurant.name_ar).where(
                    Restaurant.is_deleted.is_(False)
                )
            ).all()
            if not rows:
                print("No restaurants found.")
                return 0
            for rid, name_en, name_ar in rows:
                line = f"{rid}\t{name_en}\t{name_ar or ''}"
                try:
                    print(line)
                except UnicodeEncodeError:
                    print(line.encode("ascii", errors="replace").decode("ascii"))
            return 0

        targets: list[str] | None
        if args.all:
            targets = None
        elif args.restaurant_ids:
            targets = args.restaurant_ids
        else:
            targets = ["abuu-rest-fastfood"]

        if targets is not None:
            results = [
                YallasayMenuSeedService.seed_restaurant(
                    db,
                    rid,
                    with_offers=not args.no_offers,
                )
                for rid in targets
            ]
        else:
            results = YallasayMenuSeedService.seed_all_active(
                db,
                with_offers=not args.no_offers,
            )

        db.commit()

    total_items = sum(r.get("items", 0) for r in results)
    total_cats = sum(r.get("categories", 0) for r in results)
    total_offers = sum(r.get("offers", 0) for r in results)
    print(f"Seeded {len(results)} restaurant(s): +{total_cats} categories, +{total_items} new items, +{total_offers} new offers")
    for row in results:
        print(
            f"  {row['restaurant_id']}: categories={row['categories']} items={row['items']} offers={row['offers']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
