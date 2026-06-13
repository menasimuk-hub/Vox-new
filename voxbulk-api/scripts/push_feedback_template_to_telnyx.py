#!/usr/bin/env python3
"""Push one Customer Feedback WhatsApp template to Telnyx/Meta and print errors.

Usage (local or VPS):
  cd voxbulk-api
  source .venv/bin/activate   # Linux/VPS
  python scripts/push_feedback_template_to_telnyx.py --template-key thank_you
  python scripts/push_feedback_template_to_telnyx.py --template-id UUID
  python scripts/push_feedback_template_to_telnyx.py --template-key overall-experience --dry-run

VPS example:
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate
  python scripts/push_feedback_template_to_telnyx.py --template-key thank_you
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
    load_feedback_template,
    push_feedback_template_to_telnyx,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Push one Customer Feedback template to Telnyx")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--template-id", help="feedback_wa_templates.id (UUID)")
    group.add_argument("--template-key", help="template_key, e.g. thank_you or overall-experience")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print payload only — do not POST to Telnyx",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full result JSON on success",
    )
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        try:
            tpl = load_feedback_template(
                db,
                template_id=args.template_id,
                template_key=args.template_key,
            )
            print(f"Template: {tpl.id}  key={tpl.template_key!r}  category={tpl.meta_category}")
            print(f"Body preview: {str(tpl.body_text or '')[:120]}...")
            result = push_feedback_template_to_telnyx(db, tpl, dry_run=bool(args.dry_run))
        except FeedbackTelnyxPushError as exc:
            print("\nERROR:", exc, file=sys.stderr)
            payload = getattr(exc, "payload", None) or {}
            if payload:
                print("\nDetails:", file=sys.stderr)
                print(json.dumps(payload, indent=2, default=str), file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"\nERROR: {exc}", file=sys.stderr)
            return 1

    print("\nOK:", result.get("message"))
    print(f"Meta name: {result.get('meta_name')}")
    if args.json or args.dry_run:
        print(json.dumps(result, indent=2, default=str))
    elif result.get("telnyx_record_id"):
        print(f"Telnyx record id: {result.get('telnyx_record_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
