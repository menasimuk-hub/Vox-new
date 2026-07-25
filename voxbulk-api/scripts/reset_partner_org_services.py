#!/usr/bin/env python3
"""Reset Partner Channel orgs to normal dashboard service defaults.

Clears forced all-on overrides: inherit Admin platform grants, start with
Interview + Survey visible (same as a typical new org). Modules Admin turned
Off stay hidden.

Run on VPS from voxbulk-api/:

  .venv/bin/python scripts/reset_partner_org_services.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.services.sales_rep_service import SalesRepService  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        result = SalesRepService.reset_all_partner_org_services(db)
        print(f"OK — reset {result.get('reset', 0)} partner org(s) to default services.")
        for oid in result.get("org_ids") or []:
            print(f"  - {oid}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
