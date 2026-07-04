#!/usr/bin/env python3
"""Regenerate existing WA Survey templates with OpenAI (local drafts only).

Does NOT create industries, topics, or template rows.
Does NOT push to Meta unless --push-ids is given after review.

Examples:
  python scripts/regenerate_survey_templates_context.py --all --limit 20 --offset 0 --dry-run
  python scripts/regenerate_survey_templates_context.py --all --limit 20 --offset 0 --save
  python scripts/regenerate_survey_templates_context.py --industry-slug employee_survey --save
  python scripts/regenerate_survey_templates_context.py --push-ids 12,34,56
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="All survey industries/topics")
    parser.add_argument("--industry-slug", default="", help="Only this industry slug")
    parser.add_argument("--limit", type=int, default=20, help="Batch size (default 20)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N templates")
    parser.add_argument("--save", action="store_true", help="Persist drafts locally (no Meta)")
    parser.add_argument("--dry-run", action="store_true", help="Print only; do not save")
    parser.add_argument("--no-llm", action="store_true", help="Rule-based fallback only")
    parser.add_argument(
        "--push-ids",
        default="",
        help="Comma-separated template IDs to push to Meta (after approval only)",
    )
    args = parser.parse_args()

    from app.core.database import get_sessionmaker
    from app.services.survey_wa_context_regenerate_service import (
        list_survey_template_rows,
        push_template_ids,
        regenerate_batch,
    )
    from app.services.wa_migration_progress import migration_progress

    db = get_sessionmaker()()
    try:
        push_raw = str(args.push_ids or "").strip()
        if push_raw:
            ids = [int(x.strip()) for x in push_raw.split(",") if x.strip()]
            migration_progress(f"Pushing {len(ids)} approved template IDs to Meta …")
            result = push_template_ids(db, ids)
            print(result)
            return 0 if not result.get("failed") else 1

        if not args.all and not args.industry_slug:
            parser.error("Use --all or --industry-slug (or --push-ids)")

        industry = str(args.industry_slug or "").strip() or None
        if args.all:
            industry = None

        # Count total for progress messaging.
        all_rows = list_survey_template_rows(db, industry_slug=industry)
        migration_progress(f"Total matching templates: {len(all_rows)}")

        result = regenerate_batch(
            db,
            industry_slug=industry,
            offset=max(0, int(args.offset)),
            limit=max(1, int(args.limit)),
            save=bool(args.save),
            use_llm=not bool(args.no_llm),
            dry_run=bool(args.dry_run),
        )
        print(
            {
                "scanned": result.get("scanned"),
                "succeeded": result.get("succeeded"),
                "failed": result.get("failed"),
                "report_path": result.get("report_path"),
                "save": result.get("save"),
            }
        )
        return 0 if int(result.get("failed") or 0) == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
