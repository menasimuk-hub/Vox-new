#!/usr/bin/env python3
"""Delete WA Survey templates outside Global System Templates + Hospitality & food.

Usage (from voxbulk-api, with venv active):
  python scripts/cleanup_wa_survey_templates.py              # dry run
  python scripts/cleanup_wa_survey_templates.py --execute    # delete + set UTILITY on kept rows
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_template_cleanup_service import cleanup_wa_survey_templates


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup WA Survey templates (retained scopes only)")
    parser.add_argument("--execute", action="store_true", help="Apply deletes and category updates")
    parser.add_argument("--skip-category-update", action="store_true", help="Do not set kept templates to UTILITY")
    args = parser.parse_args()

    Session = get_sessionmaker()
    with Session() as db:
        result = cleanup_wa_survey_templates(
            db,
            dry_run=not args.execute,
            update_category_to_utility=not args.skip_category_update,
        )
    print(json.dumps(result, indent=2, default=str))
    if result.get("dry_run"):
        print("\nDry run only. Re-run with --execute to apply.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
