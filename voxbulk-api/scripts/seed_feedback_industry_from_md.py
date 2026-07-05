#!/usr/bin/env python3
"""Seed Customer Feedback industry templates from multi-language Markdown."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.customer_feedback.feedback_md_import_service import FeedbackMdImportError, FeedbackMdImportService
from app.services.customer_feedback.feedback_telnyx_push_service import push_feedback_templates_batch


def _print_dry_run(result: dict) -> None:
    print("\n=== DRY RUN — nothing written to DB or Meta ===\n")
    print(result.get("message") or "")
    print(f"\nIndustry: {result.get('industry_name')} (slug: {result.get('industry_slug')})")
    print(f"File format detected: {result.get('format_detected')}")
    if result.get("file_title"):
        print(f"File title: {result.get('file_title')}")
    print(f"Replace existing templates: {result.get('replace')}")
    print(f"Create missing topics: {result.get('create_missing_topics')}")

    summary = result.get("summary") or {}
    print("\nSummary:")
    for key, val in summary.items():
        print(f"  {key}: {val}")

    print("\nPlan (what would happen if you run with --replace):")
    for step in result.get("plan_steps") or []:
        print(f"  - {step}")

    if result.get("errors"):
        print(f"\nErrors ({len(result['errors'])}) — fix before import:")
        for e in result["errors"][:50]:
            print(f"  X {e}")
        if len(result["errors"]) > 50:
            print(f"  ... and {len(result['errors']) - 50} more")

    if result.get("warnings"):
        print(f"\nWarnings ({len(result['warnings'])}):")
        for w in result["warnings"][:30]:
            print(f"  ! {w}")
        if len(result["warnings"]) > 30:
            print(f"  ... and {len(result['warnings']) - 30} more")

    topics = result.get("topics") or []
    print(f"\nAll topics ({len(topics)}):")
    for topic in topics:
        langs = ", ".join(topic.get("languages") or [])
        print(
            f"  [{topic.get('index')}] {topic.get('name')} ({topic.get('slug')}) "
            f"- {topic.get('language_count')} langs - action={topic.get('action')} "
            f"role={topic.get('step_role')} buttons={topic.get('english_buttons')}"
        )
        if topic.get("errors"):
            for err in topic["errors"]:
                print(f"      ERROR: {err}")
        if topic.get("warnings"):
            for warn in topic["warnings"][:3]:
                print(f"      warn: {warn}")

    print("\nSample language variants (first topic, up to 3 langs):")
    if topics:
        for variant in (topics[0].get("variants_preview") or [])[:3]:
            print(
                f"  {variant.get('language')} ({variant.get('language_label')}): "
                f"{variant.get('body_preview')} | buttons={variant.get('buttons')}"
            )
        more = topics[0].get("more_language_count") or 0
        if more:
            print(f"  ... plus {more} more language(s) for this topic")

    print("\nNext step: run the same command without --dry-run (keep --replace) to import.")
    print("Meta sync is NOT automatic — use Admin Industry actions > Sync after import.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Customer Feedback templates from Markdown")
    parser.add_argument("--industry", required=True, help="Industry slug or display name")
    parser.add_argument("--md", required=True, help="Path to Markdown file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and show plan only")
    parser.add_argument("--replace", action="store_true", help="Delete existing industry templates first")
    parser.add_argument("--no-create-topics", action="store_true", help="Fail if topic missing")
    parser.add_argument("--min-langs", type=int, default=19)
    parser.add_argument("--push", action="store_true", help="After import, push to Meta in batches")
    parser.add_argument("--push-batch-size", type=int, default=5)
    parser.add_argument("--push-delay-sec", type=int, default=15)
    args = parser.parse_args()

    md_path = Path(args.md)
    if not md_path.is_absolute():
        md_path = ROOT / md_path

    with get_sessionmaker()() as db:
        try:
            if args.dry_run:
                text = md_path.read_text(encoding="utf-8")
                result = FeedbackMdImportService.import_from_text(
                    db,
                    text,
                    industry_slug=args.industry if "_" in args.industry or args.industry.islower() else None,
                    industry_name=args.industry if not (args.industry.islower() or "_" in args.industry) else None,
                    replace=args.replace or True,
                    create_missing_topics=not args.no_create_topics,
                    dry_run=True,
                    min_langs=args.min_langs,
                    source_name=md_path.name,
                )
                _print_dry_run(result)
                return 0 if result.get("ok") else 1

            result = FeedbackMdImportService.import_from_file(
                db,
                md_path,
                industry_slug=args.industry if "_" in args.industry or args.industry.islower() else None,
                industry_name=args.industry if not (args.industry.islower() or "_" in args.industry) else None,
                replace=args.replace,
                create_missing_topics=not args.no_create_topics,
                dry_run=False,
                min_langs=args.min_langs,
            )
            print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2, default=str))

            if not args.push:
                print("\nDB import complete. Sync to Meta from Admin or re-run with --push")
                return 0

            industry_id = result.get("industry_id")
            if not industry_id:
                print("No industry_id in result", file=sys.stderr)
                return 1

            offset = 0
            batch_num = 0
            while True:
                batch_num += 1
                batch = push_feedback_templates_batch(
                    db,
                    industry_id=industry_id,
                    offset=offset,
                    limit=args.push_batch_size,
                    phase="push",
                )
                print(batch.get("message") or batch)
                if not batch.get("has_more"):
                    break
                offset = int(batch.get("next_offset") or 0)
                if args.push_delay_sec > 0:
                    time.sleep(args.push_delay_sec)

            pull = push_feedback_templates_batch(db, industry_id=industry_id, phase="pull")
            print(pull.get("message") or pull)
            return 0
        except FeedbackMdImportError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
