#!/usr/bin/env python3
"""Seed themed Yallasay menus + offers into Abuu pilot restaurants.

Usage (on VPS):
  cd voxbulk-api && source .venv/bin/activate
  python scripts/seed_yallasay_full_menu.py --pilot-five
  python scripts/seed_yallasay_full_menu.py --restaurant-id abuu-rest-chicken
  python scripts/seed_yallasay_full_menu.py --restaurant-name "Sham Chicken"
  python scripts/seed_yallasay_full_menu.py --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _resolve_restaurant_ids(db, *, restaurant_ids: list[str] | None, restaurant_names: list[str] | None) -> list[str]:
    from sqlalchemy import or_, select

    from app.abuu.models.entities import Restaurant

    ids = list(restaurant_ids or [])
    for name in restaurant_names or []:
        needle = str(name).strip().lower()
        if not needle:
            continue
        row = db.execute(
            select(Restaurant.id).where(
                Restaurant.is_deleted.is_(False),
                or_(
                    Restaurant.name_en.ilike(f"%{needle}%"),
                    Restaurant.name_ar.ilike(f"%{needle}%"),
                ),
            )
        ).scalar_one_or_none()
        if row:
            ids.append(str(row))
        else:
            print(f"Warning: no restaurant matched name {name!r}", file=sys.stderr)
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Yallasay themed menus + offers")
    parser.add_argument(
        "--restaurant-id",
        action="append",
        dest="restaurant_ids",
        help="Target restaurant id (repeatable)",
    )
    parser.add_argument(
        "--restaurant-name",
        action="append",
        dest="restaurant_names",
        help='Match restaurant by name (e.g. "Sham Chicken")',
    )
    parser.add_argument("--pilot-five", action="store_true", help="Seed all 5 Gaza pilot restaurants")
    parser.add_argument("--all", action="store_true", help="Seed every active restaurant")
    parser.add_argument("--list", action="store_true", help="List restaurant ids and exit")
    parser.add_argument("--no-offers", action="store_true", help="Skip promo offers")
    args = parser.parse_args()

    from sqlalchemy import select

    from app.abuu.models.entities import Restaurant
    from app.abuu.services.seed_service import AbuuSeedService
    from app.abuu.services.yallasay_menu_catalog import YALLASAY_PILOT_RESTAURANT_IDS
    from app.abuu.services.yallasay_menu_seed_service import YallasayMenuSeedService
    from app.abuu.services.yallasay_wa_snapshot_service import YallasayWaSnapshotService
    from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations

    run_abuu_migrations()

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.ensure_pilot_restaurants(db)
        YallasayWaSnapshotService.ensure_gaza_market_agent(db)
        db.commit()

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
                pilot = " [pilot]" if rid in YALLASAY_PILOT_RESTAURANT_IDS else ""
                line = f"{rid}\t{name_en}\t{name_ar or ''}{pilot}"
                try:
                    print(line)
                except UnicodeEncodeError:
                    print(line.encode("ascii", errors="replace").decode("ascii"))
            return 0

        if args.pilot_five:
            results = YallasayMenuSeedService.seed_pilot_five(db, with_offers=not args.no_offers)
        elif args.all:
            results = YallasayMenuSeedService.seed_all_active(db, with_offers=not args.no_offers)
        else:
            targets = _resolve_restaurant_ids(
                db,
                restaurant_ids=args.restaurant_ids,
                restaurant_names=args.restaurant_names,
            )
            if not targets:
                targets = ["abuu-rest-chicken"]
            results = YallasayMenuSeedService.seed_all_active(
                db,
                with_offers=not args.no_offers,
                restaurant_ids=targets,
            )

        for row in results:
            if not row.get("error"):
                YallasayWaSnapshotService.rebuild_restaurant(db, row["restaurant_id"])
        YallasayWaSnapshotService.rebuild_marketplace(db)
        db.commit()

    total_items = sum(r.get("items", 0) for r in results)
    total_cats = sum(r.get("categories", 0) for r in results)
    total_offers = sum(r.get("offers", 0) for r in results)
    errors = [r for r in results if r.get("error")]
    print(
        f"Seeded {len(results)} restaurant(s): +{total_cats} categories, "
        f"+{total_items} new items, +{total_offers} new offers"
    )
    for row in results:
        if row.get("error"):
            print(f"  {row['restaurant_id']}: ERROR — {row['error']}")
        else:
            print(
                f"  {row['restaurant_id']}: categories={row['categories']} "
                f"items={row['items']} offers={row['offers']}"
            )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
