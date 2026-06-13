#!/usr/bin/env python3
"""Push all Customer Feedback WhatsApp templates for one industry to Telnyx/Meta.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python scripts/push_feedback_industry_to_telnyx.py --industry-slug fitness --dry-run
  python scripts/push_feedback_industry_to_telnyx.py --industry-slug fitness

Fitness & gyms has 20 survey templates (01–20 in english-templates.md).
Import templates in Admin first, then run this script.
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
from app.services.customer_feedback.feedback_telnyx_push_service import (
    FeedbackTelnyxPushError,
    push_all_feedback_templates_for_industry,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Push all Customer Feedback templates for one industry to Telnyx"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--industry-slug", help="Industry slug, e.g. fitness, events, restaurant")
    group.add_argument("--industry-id", help="feedback_industries.id (UUID)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate payloads only — do not POST to Telnyx",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full summary JSON at the end",
    )
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        try:
            summary = push_all_feedback_templates_for_industry(
                db,
                industry_id=args.industry_id,
                industry_slug=args.industry_slug,
                dry_run=bool(args.dry_run),
            )
        except FeedbackTelnyxPushError as exc:
            print(f"\nERROR: {exc}", file=sys.stderr)
            payload = getattr(exc, "payload", None) or {}
            if payload:
                print(json.dumps(payload, indent=2, default=str), file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"\nERROR: {exc}", file=sys.stderr)
            return 1

    print(f"Industry: {summary.get('industry_name')} ({summary.get('industry_slug')})")
    print(f"Templates: {summary.get('template_count', 0)}")
    print(summary.get("message") or summary)

    for item in summary.get("results") or []:
        key = item.get("template_key") or item.get("template_id")
        if item.get("ok"):
            meta = item.get("meta_name") or ""
            print(f"  OK   {key}" + (f" → {meta}" if meta else ""))
        else:
            print(f"  FAIL {key}: {item.get('error')}", file=sys.stderr)

    if args.json:
        print(json.dumps(summary, indent=2, default=str))

    failed = int(summary.get("failed") or 0)
    if failed:
        print(f"\n{failed} template(s) failed — see errors above.", file=sys.stderr)
        first = (summary.get("errors") or [{}])[0]
        detail = first.get("payload") or {}
        telnyx = detail.get("telnyx_response")
        if telnyx:
            print("\nFirst failure Telnyx response:", file=sys.stderr)
            print(json.dumps(telnyx, indent=2, default=str), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
