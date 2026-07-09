#!/usr/bin/env python3
"""Purge Marketing WA templates: rewrite survey rows to UTILITY, delete old Meta/Telnyx + DB rows.

Default is dry-run only (prints full plan). To apply:
  .venv/bin/python scripts/purge_marketing_wa_templates.py --apply --push
  (prompts: type PUSH to confirm; one Meta push every 30s)

VPS:
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python scripts/purge_marketing_wa_templates.py
  .venv/bin/python scripts/purge_marketing_wa_templates.py --apply --push --yes
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
from app.services.wa_marketing_purge_service import apply_purge_plan, build_marketing_purge_plan

REPORT_DIR = ROOT / "seed-data" / "wa-survey" / "migration-reports"


def _print_plan_item(index: int, item) -> None:
    print(f"\n[{index}] {item.action} | {item.product} | {item.label}")
    if item.old_meta_name and item.old_meta_name != item.new_meta_name:
        print(f"    delete remote: {item.old_meta_name}")
    if item.new_meta_name and item.new_meta_name != item.label:
        print(f"    new name:      {item.new_meta_name}")
    preview = item.dry_preview or {}
    if preview.get("body_before"):
        print(f"    was: {str(preview['body_before'])[:120]}…")
    if preview.get("body_after"):
        print(f"    now: {str(preview['body_after'])[:120]}…")
    if item.meta:
        reasons = item.meta.get("reasons") or item.meta.get("note")
        if reasons:
            print(f"    meta: {reasons}")


def _confirm_push() -> bool:
    print("\n" + "=" * 60)
    print("Dry-run plan shown above.")
    print("This will REWRITE survey templates, PUSH to Meta (1 every 30s),")
    print("and DELETE old Marketing templates from Meta, Telnyx, and DB.")
    print("Type PUSH to continue (anything else aborts): ", end="", flush=True)
    try:
        return input().strip().upper() == "PUSH"
    except EOFError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge Marketing WA templates (survey + customer feedback)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply plan (default: dry-run only)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="With --apply: push rewritten templates to Meta (30s between pushes)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip PUSH confirmation prompt",
    )
    parser.add_argument(
        "--sync-remote",
        action="store_true",
        help="Refresh each survey row from Meta/Telnyx before rewrite",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Rule-based survey rewrite only (recommended for NPS/recommend topics)",
    )
    parser.add_argument(
        "--push-delay",
        type=float,
        default=30.0,
        help="Seconds between Meta pushes (default 30)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Apply at most N plan items (0 = all)",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    if args.apply and args.push and not args.yes and not _confirm_push():
        print("Aborted.", file=sys.stderr)
        return 1

    db = get_sessionmaker()()
    try:
        overview, plan = build_marketing_purge_plan(db)
    finally:
        db.close()

    print("=" * 60)
    print("MARKETING PURGE PLAN (dry-run)" if dry_run else "MARKETING PURGE APPLY")
    print("=" * 60)
    sr = overview.get("survey_remote") or {}
    cfr = overview.get("customer_feedback_remote") or {}
    print(
        f"Survey live marketing — Meta: {sr.get('remote_marketing_meta', '—')}, "
        f"Telnyx: {sr.get('remote_marketing_telnyx', '—')}"
    )
    print(
        f"CF live marketing — Meta: {cfr.get('remote_marketing_meta', '—')}, "
        f"Telnyx: {cfr.get('remote_marketing_telnyx', '—')}"
    )
    counts = overview.get("plan_counts") or {}
    print(f"Plan items: {overview.get('total_items', len(plan))} (pushes: {overview.get('push_items', 0)})")
    for action, count in sorted(counts.items()):
        if count:
            print(f"  {action}: {count}")

    work_plan = plan[: args.limit] if args.limit and args.limit > 0 else plan
    for index, item in enumerate(work_plan, start=1):
        _print_plan_item(index, item)

    if dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / f"marketing-purge-dryrun-{stamp}.json"
        report_path.write_text(
            json.dumps(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "dry_run": True,
                    "overview": overview,
                    "plan": [p.to_dict() for p in work_plan],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nDry-run only. Report: {report_path}")
        print("To apply:  python scripts/purge_marketing_wa_templates.py --apply --push")
        return 0

    with get_sessionmaker()() as db:
        results = apply_purge_plan(
            db,
            work_plan,
            dry_run=False,
            push=bool(args.push),
            sync_remote=bool(args.sync_remote),
            use_llm=not args.no_llm,
            push_delay_seconds=max(0.0, float(args.push_delay)),
        )

    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok
    for result in results:
        status = "OK" if result.get("ok") else "FAIL"
        line = f"{status} [{result.get('index')}/{result.get('total')}] {result.get('action')} {result.get('label')}"
        if result.get("error"):
            line += f" — {result['error']}"
        elif result.get("new_name"):
            line += f" → {result['new_name']}"
        elif result.get("deleted_remote"):
            line += f" deleted {result['deleted_remote']}"
        print(line, flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"marketing-purge-apply-{stamp}.json"
    report_path.write_text(
        json.dumps(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "dry_run": False,
                "pushed": bool(args.push),
                "overview": overview,
                "ok": ok,
                "failed": fail,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nDone: {ok} ok, {fail} failed. Report: {report_path}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
