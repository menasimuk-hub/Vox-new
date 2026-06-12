#!/usr/bin/env python3
"""Rewrite WA survey templates for Meta UTILITY (Feedback Survey) and optionally push via Telnyx.

Meta recategorized generic satisfaction surveys as MARKETING. UTILITY feedback templates must:
- Reference a specific recent interaction (visit, service, order, engagement)
- Stay non-promotional (no offers, upsell, or persuasive marketing tone)
- Preserve leading emojis when present; avoid vague "we'd love your feedback" openers
- --push resubmits APPROVED templates to Meta for re-review (UTILITY category + new BODY)

See: https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization

Usage (local):
  cd voxbulk-api
  .venv/bin/python scripts/rewrite_wa_survey_templates_for_utility.py --dry-run
  .venv/bin/python scripts/rewrite_wa_survey_templates_for_utility.py --sync-remote --push
  .venv/bin/python scripts/rewrite_wa_survey_templates_for_utility.py --names-file seed-data/wa-survey/utility-rewrite-template-names.txt --push

VPS (recommended):
  cd /www/voxbulk/voxbulk-api
  bash scripts/rewrite_wa_survey_templates_for_utility.sh --sync-remote --push
  cd /www/voxbulk && bash vox.sh restart
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_utility_rewrite_service import (
    load_template_names_from_file,
    process_template_names,
)

DEFAULT_NAMES_FILE = ROOT / "seed-data/wa-survey/utility-rewrite-template-names.txt"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite WA survey templates for Meta UTILITY category and push to Telnyx"
    )
    parser.add_argument(
        "--names-file",
        default=str(DEFAULT_NAMES_FILE),
        help="Text file with one template name per line (default: bundled employee/industrial list)",
    )
    parser.add_argument(
        "--template-name",
        action="append",
        default=[],
        help="Single template name (repeatable); overrides --names-file when provided",
    )
    parser.add_argument(
        "--sync-remote",
        action="store_true",
        help="Refresh each template from Telnyx before rewriting (recommended)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push rewritten drafts to Telnyx/Meta after saving",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview rewritten BODY text without saving or pushing",
    )
    parser.add_argument(
        "--no-deepseek",
        action="store_true",
        help="Use rule-based rewrite only (no DeepSeek API call)",
    )
    args = parser.parse_args()

    if args.template_name:
        names = [n.strip() for n in args.template_name if str(n or "").strip()]
    else:
        path = Path(args.names_file)
        if not path.is_file():
            print(f"Names file not found: {path}", file=sys.stderr)
            return 1
        names = load_template_names_from_file(str(path))

    if not names:
        print("No template names to process", file=sys.stderr)
        return 1

    ok_count = 0
    fail_count = 0

    with get_sessionmaker()() as db:
        results = process_template_names(
            db,
            names,
            sync_remote=bool(args.sync_remote),
            push=bool(args.push) and not args.dry_run,
            dry_run=bool(args.dry_run),
            use_deepseek=not args.no_deepseek,
        )

    for item in results:
        if item.ok:
            ok_count += 1
            print(f"OK  {item.template_name}", flush=True)
            if item.old_body:
                print(f"    was: {item.old_body[:120]}{'…' if len(item.old_body) > 120 else ''}", flush=True)
            if item.new_body:
                print(f"    now: {item.new_body[:120]}{'…' if len(item.new_body) > 120 else ''}", flush=True)
            if item.message:
                print(f"    {item.message}", flush=True)
        else:
            fail_count += 1
            print(f"FAIL {item.template_name}: {item.message}", file=sys.stderr, flush=True)

    print(f"\nDone: {ok_count} ok, {fail_count} failed, {len(results)} total")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
