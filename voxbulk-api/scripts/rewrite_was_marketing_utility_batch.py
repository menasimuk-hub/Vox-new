#!/usr/bin/env python3
"""Batch rewrite was_* WA survey templates with bad English / Marketing classification.

Finds templates whose BODY still uses NPS/recommend wording or failed Meta utility lint,
rewrites to industry-aware UTILITY copy, bumps was_* sequence when Meta blocks category
changes on APPROVED rows (_002_ -> _003_), then optionally pushes to Meta/Telnyx.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python scripts/rewrite_was_marketing_utility_batch.py --discover
  .venv/bin/python scripts/rewrite_was_marketing_utility_batch.py --dry-run --name-contains would_recommend
  .venv/bin/python scripts/rewrite_was_marketing_utility_batch.py --sync-remote --push --name-contains would_recommend
  .venv/bin/python scripts/rewrite_was_marketing_utility_batch.py --sync-remote --push --no-llm --limit 5
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
    discover_was_utility_rewrite_candidates,
    process_template_names,
)

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch UTILITY rewrite for was_* templates (bad English / Marketing bodies)"
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="List candidate templates and exit (no rewrite)",
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
        help="Re-push even when local row is already UTILITY on Meta",
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
    try:
        candidates = discover_was_utility_rewrite_candidates(
            db,
            name_contains=args.name_contains or None,
            industry_slug=args.industry or None,
        )
    finally:
        db.close()

    if args.limit and args.limit > 0:
        candidates = candidates[: args.limit]

    if args.discover:
        print(json.dumps(candidates, indent=2, ensure_ascii=False))
        print(f"\n{candidates and len(candidates) or 0} candidate(s)")
        return 0

    if not candidates:
        print("No was_* templates need utility rewrite for the current filters.", file=sys.stderr)
        return 0

    names = [str(item["name"]) for item in candidates if item.get("name")]
    print(f"Processing {len(names)} template(s)…", flush=True)

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
            skip_already_pushed=not args.force,
            push_delay_seconds=max(0.0, float(args.push_delay or 0)),
        )

    ok_count = 0
    fail_count = 0
    report_rows: list[dict] = []
    candidate_by_name = {str(c["name"]): c for c in candidates if c.get("name")}

    for item in results:
        candidate = candidate_by_name.get(item.template_name, {})
        entry = {
            "name": item.template_name,
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
                "dry_run": bool(args.dry_run),
                "pushed": bool(args.push),
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
