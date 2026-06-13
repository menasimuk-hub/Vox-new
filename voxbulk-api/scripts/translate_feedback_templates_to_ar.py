#!/usr/bin/env python3
"""Translate Customer Feedback templates to Arabic (OpenAI JSON API) and push to Telnyx.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api && source .venv/bin/activate

  # Preview one industry (no API writes)
  python scripts/translate_feedback_templates_to_ar.py --industry-slug fitness --dry-run --limit 2

  # Translate all industries to Arabic
  python scripts/translate_feedback_templates_to_ar.py

  # Translate + push Arabic templates to Telnyx/Meta
  python scripts/translate_feedback_templates_to_ar.py --push-telnyx

  # Re-translate and push fitness only
  python scripts/translate_feedback_templates_to_ar.py --industry-slug fitness --force --push-telnyx

Requires OpenAI configured in Admin → Integrations → OpenAI (default).
Use --provider deepseek to fall back to DeepSeek chat API.
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
from app.services.customer_feedback.feedback_template_translation_service import (
    FeedbackTemplateTranslationError,
    translate_templates_to_arabic,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate Customer Feedback templates to Arabic")
    parser.add_argument("--industry-slug", help="Only this industry, e.g. fitness, restaurant")
    parser.add_argument("--force", action="store_true", help="Re-translate even if Arabic row exists")
    parser.add_argument("--push-telnyx", action="store_true", help="Push Arabic templates to Telnyx after translate")
    parser.add_argument("--dry-run", action="store_true", help="Translate only — do not save or push")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM (structure test only)")
    parser.add_argument(
        "--provider",
        default="openai",
        choices=["openai", "deepseek"],
        help="Translation provider (default: openai structured JSON API)",
    )
    parser.add_argument("--limit", type=int, help="Max templates to process")
    parser.add_argument("--json", action="store_true", help="Print full summary JSON")
    args = parser.parse_args()

    with get_sessionmaker()() as db:
        try:
            summary = translate_templates_to_arabic(
                db,
                industry_slug=args.industry_slug,
                force=bool(args.force),
                use_llm=not args.no_llm,
                provider=str(args.provider or "openai"),
                push_telnyx=bool(args.push_telnyx),
                dry_run=bool(args.dry_run),
                limit=args.limit,
            )
        except FeedbackTemplateTranslationError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    print(summary.get("message") or summary)
    print(f"Sources: {summary.get('source_count')}  translated: {summary.get('translated')}  skipped: {summary.get('skipped')}")
    if args.push_telnyx:
        print(f"Pushed: {summary.get('pushed')}  push failed: {summary.get('push_failed')}")

    for err in summary.get("errors") or []:
        print(
            f"  FAIL [{err.get('stage')}] {err.get('template_key')}: {err.get('error')}",
            file=sys.stderr,
        )

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))

    failed = len(summary.get("errors") or []) + int(summary.get("push_failed") or 0)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
