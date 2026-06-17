#!/usr/bin/env python3
"""Seed 7 demo restaurant + 3 demo driver portal accounts for YallaSay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.abuu.services.yallasay_demo_seed_service import YallasayDemoSeedService
from app.core.abuu_database import get_abuu_sessionmaker


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed YallaSay demo restaurant/driver accounts")
    parser.add_argument("--no-offers", action="store_true", help="Skip promo offer upsert")
    args = parser.parse_args()

    with get_abuu_sessionmaker()() as db:
        result = YallasayDemoSeedService.seed_all(db, with_offers=not args.no_offers)
        db.commit()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nEnable internal pages: ABUU_DEMO_SHOWALL_ENABLED=true then ./vox.sh restart")
    print("Restaurant showall: https://restaurant.yallasay.com/showall")
    print("Driver showall: https://driver.yallasay.com/showall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
