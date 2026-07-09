#!/usr/bin/env python3
"""Batch rewrite WA survey templates live-classified as Marketing on Meta/Telnyx.

Default discovery reads live remote categories (admin matrix: Meta marketing / Telnyx marketing),
not local DB category — Meta often reclassifies while local rows still show UTILITY.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python scripts/rewrite_was_marketing_utility_batch.py --discover
  .venv/bin/python scripts/rewrite_was_marketing_utility_batch.py --discover --include-non-actionable
  .venv/bin/python scripts/rewrite_was_marketing_utility_batch.py --dry-run --limit 5
  .venv/bin/python scripts/rewrite_was_marketing_utility_batch.py --sync-remote --push --no-llm
  .venv/bin/python scripts/rewrite_was_marketing_utility_batch.py --discover --source local
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_utility_rewrite_service import (
    discover_remote_marketing_survey_templates,
    discover_was_utility_rewrite_candidates,
    process_template_names,
)

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch UTILITY rewrite for survey templates live-classified as Marketing"
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="List candidate templates and exit (no rewrite)",
    )
    parser.add_argument(
        "--source",
        choices=("remote", "local"),
        default="remote",
        help="remote = live Meta/Telnyx MARKETING (default); local = DB-only heuristics",
    )
    parser.add_argument(
        "--include-non-actionable",
        action="store_true",
        help="With --discover, include remote marketing rows with no local DB match",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview rewritten BODY text without saving or pushing",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save rewritten templates to DB (without pushing)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push rewritten drafts to Telnyx/Meta after saving",
    )
    parser.add_argument(
        "--sync-remote",
        action="store_true",
        help="Refresh each template from Telnyx/Meta before rewriting",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Rule-based rewrite only (recommended for would_recommend / NPS topics)",
    )
    parser.add_argument(
        "--name-contains",
        default="",
        help="Filter template names (e.g. would_recommend)",
    )
    parser.add_argument(
        "--industry",
        default="",
        help="Filter by industry slug (e.g. logistics_delivery)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N templates (0 = all candidates)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-push even when local row looks UTILITY+APPROVED (remote mode ignores skip by default)",
    )
    parser.add_argument(
        "--push-delay",
        type=float,
        default=1.5,
        help="Seconds between Meta pushes (default 1.5)",
    )
    args = parser.parse_args()

    if args.push:
        args.save = True

    if not args.discover and not args.dry_run and not args.save and not args.push:
        parser.error("Specify --discover, --dry-run, --save, and/or --push")

    db = get_sessionmaker()()
    overview: dict = {}
    try:
        if args.discover and args.source == "remote":
            overview, all_candidates = discover_remote_marketing_survey_templates(
                db,
                name_contains=args.name_contains or None,
                industry_slug=args.industry or None,
            )
            candidates = all_candidates if args.include_non_actionable else [
                item for item in all_candidates if item.get("actionable")
            ]
        else:
            candidates = discover_was_utility_rewrite_candidates(
                db,
                name_contains=args.name_contains or None,
                industry_slug=args.industry or None,
                source=args.source,
            )
            all_candidates = candidates
    finally:
        db.close()

    if args.discover:
        payload = {
            "overview": overview,
            "candidates": candidates,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if overview:
            print(
                f"\nLive marketing — Meta: {overview.get('remote_marketing_meta', '—')}, "
                f"Telnyx: {overview.get('remote_marketing_telnyx', '—')}, "
                f"unique remote: {overview.get('unique_remote_marketing', '—')}, "
                f"actionable local matches: {overview.get('actionable_local_matches', len(candidates))}"
            )
        print(f"\n{len(candidates)} candidate(s) listed")
        return 0

    if args.limit and args.limit > 0:
        candidates = candidates[: args.limit]

    if not candidates:
        print("No survey templates need utility rewrite for the current filters.", file=sys.stderr)
        return 0

    names = [
        str(item.get("process_name") or item.get("name"))
        for item in candidates
        if item.get("process_name") or item.get("name")
    ]
    print(f"Processing {len(names)} template(s)…", flush=True)

    skip_already = args.force is False and args.source == "local"

    with get_sessionmaker()() as db:
        results = process_template_names(
            db,
            names,
            sync_remote=bool(args.sync_remote),
            save=bool(args.save) and not args.dry_run,
            push=bool(args.push) and not args.dry_run,
            dry_run=bool(args.dry_run),
            use_llm=not args.no_llm,
            llm_provider="openai",
            skip_already_pushed=skip_already,
            push_delay_seconds=max(0.0, float(args.push_delay or 0)),
        )

    ok_count = 0
    fail_count = 0
    report_rows: list[dict] = []
    candidate_by_name = {
        str(c.get("process_name") or c.get("name")): c for c in candidates if c.get("process_name") or c.get("name")
    }

    for item in results:
        candidate = candidate_by_name.get(item.template_name, {})
        entry = {
            "name": item.template_name,
            "remote_name": candidate.get("remote_name"),
            "ok": item.ok,
            "message": item.message,
            "pushed": item.pushed,
            "reasons": candidate.get("reasons"),
            "old_body": item.old_body,
            "new_body": item.new_body,
        }
        report_rows.append(entry)
        if item.ok:
            ok_count += 1
            print(f"OK  {item.template_name}", flush=True)
            if item.old_body:
                print(
                    f"    was: {item.old_body[:120]}{'…' if len(item.old_body) > 120 else ''}",
                    flush=True,
                )
            if item.new_body and item.new_body != item.old_body:
                print(
                    f"    now: {item.new_body[:120]}{'…' if len(item.new_body) > 120 else ''}",
                    flush=True,
                )
            if item.message:
                print(f"    {item.message}", flush=True)
        else:
            fail_count += 1
            print(f"FAIL {item.template_name}: {item.message}", file=sys.stderr, flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"was-utility-rewrite-{stamp}.json"
    report_path.write_text(
        json.dumps(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "source": args.source,
                "dry_run": bool(args.dry_run),
                "pushed": bool(args.push),
                "overview": overview,
                "filters": {
                    "name_contains": args.name_contains or None,
                    "industry": args.industry or None,
                    "limit": args.limit or None,
                },
                "ok": ok_count,
                "failed": fail_count,
                "results": report_rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"\nDone: {ok_count} ok, {fail_count} failed, {len(results)} total")
    print(f"report={report_path}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
