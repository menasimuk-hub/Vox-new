#!/usr/bin/env python3
"""Full DB audit for WA UTILITY migration — duplicates, orphans, missing AR pairs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.wa_template_utility_migration_service import (
    audit_all_wa_templates,
    deactivate_duplicate_and_orphan_templates,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit WA templates in DB for UTILITY migration")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dedup", action="store_true", help="Deactivate duplicate/orphan rows after audit")
    parser.add_argument("--dry-run", action="store_true", help="With --dedup: report only, no DB writes")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        audit = audit_all_wa_templates(db)
        dedup = None
        if args.dedup:
            dedup = deactivate_duplicate_and_orphan_templates(db, dry_run=args.dry_run)

    payload = {"audit": audit, "dedup": dedup}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"Survey abc_choice: {audit['survey']['abc_choice_total']}")
        print(f"Survey orphans: {audit['survey']['orphan_count']}")
        print(f"Survey duplicate extras: {audit['survey']['duplicate_rows']}")
        print(f"Feedback EN utility: {audit['feedback']['english_utility']}")
        print(f"Feedback missing AR: {audit['feedback']['missing_ar_pair']}")
        if dedup:
            print(f"Dedup survey deactivated: {dedup['deactivated_survey']}")
            print(f"Dedup feedback deactivated: {dedup['deactivated_feedback']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
