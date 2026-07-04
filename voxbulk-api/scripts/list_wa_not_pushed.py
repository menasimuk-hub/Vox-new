#!/usr/bin/env python3
"""List buttoned WA Survey templates not APPROVED/PENDING on Meta.

Buttonless templates are counted separately and never mixed into the main list.

Usage:
  cd voxbulk-api && source .venv/bin/activate
  python3 scripts/list_wa_not_pushed.py
  python3 scripts/list_wa_not_pushed.py --industry-slug employee_survey
  python3 scripts/list_wa_not_pushed.py --name-like interview --json
  python3 scripts/list_wa_not_pushed.py --export /tmp/not-pushed-names.txt
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

from scripts.wa_not_pushed_lib import (
    is_not_on_meta,
    iter_survey_keeper_rows,
    row_summary,
    split_buttoned_buttonless,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="List buttoned survey templates not on Meta")
    parser.add_argument("--industry-slug", default="", help="Filter to one industry")
    parser.add_argument("--name-like", default="", help="Filter template name (SQL ILIKE)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--export", default="", help="Write buttoned not-pushed names one per line")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        try:
            keepers = iter_survey_keeper_rows(
                db,
                industry_slug=args.industry_slug.strip() or None,
                name_like=args.name_like.strip() or None,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        buttoned, buttonless = split_buttoned_buttonless(keepers)
        not_pushed = [row for row in buttoned if is_not_on_meta(row)]
        summaries = [row_summary(db, row) for row in not_pushed]

    if args.json:
        print(
            json.dumps(
                {
                    "buttoned_not_on_meta": len(summaries),
                    "buttoned_total": len(buttoned),
                    "buttonless_skipped": len(buttonless),
                    "templates": summaries,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"Buttoned (in scope):        {len(buttoned)}")
        print(f"Buttoned not on Meta:       {len(not_pushed)}")
        print(f"Buttonless (skipped):       {len(buttonless)}")
        print()
        if not not_pushed:
            print("No buttoned templates need Meta push for this filter.")
        else:
            print(f"{'BTNS':<5} {'STATUS':<12} {'LANG':<8} {'INDUSTRY':<22} NAME")
            print("-" * 110)
            for item in summaries:
                print(
                    f"{item['button_count']:<5} "
                    f"{str(item['status'] or ''):<12} "
                    f"{str(item['language'] or ''):<8} "
                    f"{str(item['industry_slug'] or ''):<22} "
                    f"{item['name']}"
                )
                if item.get("last_push_error"):
                    print(f"      error: {item['last_push_error'][:120]}")

    if args.export:
        path = Path(args.export)
        path.write_text("\n".join(item["name"] for item in summaries) + ("\n" if summaries else ""), encoding="utf-8")
        print(f"\nExported {len(summaries)} name(s) → {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
