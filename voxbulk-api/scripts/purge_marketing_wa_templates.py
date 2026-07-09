#!/usr/bin/env python3
"""Marketing → UTILITY cleanup — 5 clear steps (VPS).

DeepInfra API key comes from Admin → Integrations → DeepInfra (DB). No .env changes.
Rewrites use Qwen2.5 72B via DeepInfra. Push goes to Meta (+447822002099) AND Telnyx (+447822002055).

WORKFLOW (run from /www/voxbulk/voxbulk-api):

  Step 1 — list MARKETING templates (read-only):
    .venv/bin/python scripts/purge_marketing_wa_templates.py list-marketing

  Step 2 — you approve which templates to rewrite:
    .venv/bin/python scripts/purge_marketing_wa_templates.py approve-rewrite --batch-id BATCH --all
    .venv/bin/python scripts/purge_marketing_wa_templates.py approve-rewrite --batch-id BATCH --names was_hotel_*

  Step 3 — Qwen rewrites approved templates, prints before/after:
    .venv/bin/python scripts/purge_marketing_wa_templates.py rewrite --batch-id BATCH

  Step 4 — you approve which rewrites to push live:
    .venv/bin/python scripts/purge_marketing_wa_templates.py approve-push --batch-id BATCH --all

  Step 5 — push to Meta + Telnyx, delete old MARKETING names:
    .venv/bin/python scripts/purge_marketing_wa_templates.py push --batch-id BATCH --yes

Review files (full before/after): seed-data/wa-survey/migration-reports/marketing-utility-review/BATCH/
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_utility_rewrite_service import resolve_utility_llm_config
from app.services.wa_marketing_purge_service import apply_purge_plan, manifest_items_to_plan
from app.services.wa_marketing_review_service import (
    approve_manifest_items,
    create_marketing_list_manifest,
    load_manifest,
    print_listed_templates,
    print_rewritten_templates,
    review_batch_dir,
    run_batch_rewrites,
)


def _default_batch_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _parse_names(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


def _parse_ids(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


def _confirm_push() -> bool:
    print("\nPushes to Meta (+447822002099) AND Telnyx (+447822002055). ~30s between each.")
    print("Type PUSH to continue: ", end="", flush=True)
    try:
        return input().strip().upper() == "PUSH"
    except EOFError:
        return False


def cmd_list_marketing(args: argparse.Namespace) -> int:
    batch_id = str(args.batch_id or _default_batch_id()).strip()
    db = get_sessionmaker()()
    try:
        try:
            llm_cfg = resolve_utility_llm_config(db)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        manifest = create_marketing_list_manifest(
            db,
            batch_id=batch_id,
            name_contains=args.name_contains,
            limit=args.limit or 0,
        )
    finally:
        db.close()

    print(f"DeepInfra: configured (Admin DB) | model for rewrite: {llm_cfg['model']}")
    print(f"Base URL:  {llm_cfg['base_url']}")
    print("")
    print_listed_templates(manifest)
    print(f"\nManifest saved: {review_batch_dir(batch_id)}")
    return 0


def cmd_approve_rewrite(args: argparse.Namespace) -> int:
    batch_id = str(args.batch_id or "").strip()
    if not batch_id:
        print("--batch-id is required", file=sys.stderr)
        return 1
    if not args.all and not args.names and not args.ids:
        print("Use --all, --names, or --ids", file=sys.stderr)
        return 1
    result = approve_manifest_items(
        batch_id,
        names=_parse_names(args.names),
        ids=_parse_ids(args.ids),
        approve_all=bool(args.all),
        from_status="listed",
        to_status="approved_rewrite",
    )
    print(f"Approved {result.get('approved', 0)} template(s) for rewrite.")
    print(f"Status counts: {result.get('status_counts')}")
    print(f"\nNEXT:\n  python scripts/purge_marketing_wa_templates.py rewrite --batch-id {batch_id}")
    return 0


def cmd_rewrite(args: argparse.Namespace) -> int:
    batch_id = str(args.batch_id or "").strip()
    if not batch_id:
        print("--batch-id is required", file=sys.stderr)
        return 1
    db = get_sessionmaker()()
    try:
        result = run_batch_rewrites(
            db,
            batch_id=batch_id,
            use_llm=not args.no_llm,
            limit_groups=args.limit or 0,
        )
        manifest = load_manifest(batch_id)
    finally:
        db.close()
    print(f"Rewrote {result.get('rewritten', 0)} template(s) using {result.get('llm_model')}.")
    print(f"Status counts: {result.get('status_counts')}")
    print("")
    print_rewritten_templates(manifest)
    return 0


def cmd_show_rewrites(args: argparse.Namespace) -> int:
    batch_id = str(args.batch_id or "").strip()
    if not batch_id:
        print("--batch-id is required", file=sys.stderr)
        return 1
    manifest = load_manifest(batch_id)
    print_rewritten_templates(manifest)
    return 0


def cmd_approve_push(args: argparse.Namespace) -> int:
    batch_id = str(args.batch_id or "").strip()
    if not batch_id:
        print("--batch-id is required", file=sys.stderr)
        return 1
    if not args.all and not args.names and not args.ids:
        print("Use --all, --names, or --ids", file=sys.stderr)
        return 1
    result = approve_manifest_items(
        batch_id,
        names=_parse_names(args.names),
        ids=_parse_ids(args.ids),
        approve_all=bool(args.all),
        from_status="rewritten",
        to_status="approved_push",
    )
    print(f"Approved {result.get('approved', 0)} template(s) for live push.")
    print(f"Status counts: {result.get('status_counts')}")
    print(f"\nNEXT:\n  python scripts/purge_marketing_wa_templates.py push --batch-id {batch_id} --yes")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    batch_id = str(args.batch_id or "").strip()
    if not batch_id:
        print("--batch-id is required", file=sys.stderr)
        return 1
    manifest = load_manifest(batch_id)
    plan = manifest_items_to_plan(manifest, approved_only=True)
    if args.limit and args.limit > 0:
        plan = plan[: args.limit]
    if not plan:
        print("No items with status=approved_push. Run approve-push first.", file=sys.stderr)
        return 1

    print("=" * 72)
    print("STEP 5 — PUSH to Meta + Telnyx")
    print("=" * 72)
    print(f"Batch: {batch_id} | items: {len(plan)}")
    for i, item in enumerate(plan, start=1):
        preview = item.dry_preview or {}
        print(f"  [{i}] {item.old_meta_name or item.label} → {item.new_meta_name}")
        print(f"       after: {str(preview.get('body_after') or '')[:100]}…")
    if not args.yes and not _confirm_push():
        print("Aborted.", file=sys.stderr)
        return 1

    db = get_sessionmaker()()
    try:
        llm_cfg = resolve_utility_llm_config(db)
        results = apply_purge_plan(
            db,
            plan,
            dry_run=False,
            push=True,
            sync_remote=bool(args.sync_remote),
            use_llm=False,
            llm_provider=llm_cfg["provider"],
            llm_model=llm_cfg["model"],
            push_delay_seconds=max(0.0, float(args.push_delay)),
            batch_id=batch_id,
        )
    finally:
        db.close()

    ok = sum(1 for r in results if r.get("ok"))
    fail = len(results) - ok
    print(f"\nDone: {ok} pushed, {fail} failed.")
    return 0 if fail == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Marketing → UTILITY: list → approve rewrite → rewrite → approve push → push",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("list-marketing", help="Step 1: pull + show MARKETING templates")
    p1.add_argument("--batch-id", default=None, help=f"Batch folder name (default: today {_default_batch_id()})")
    p1.add_argument("--limit", type=int, default=0, help="Max templates (0=all)")
    p1.add_argument("--name-contains", default=None)
    p1.set_defaults(func=cmd_list_marketing)

    p2 = sub.add_parser("approve-rewrite", help="Step 2: approve templates for Qwen rewrite")
    p2.add_argument("--batch-id", required=True)
    p2.add_argument("--names", default=None, help="Comma-separated names or prefix*")
    p2.add_argument("--ids", default=None, help="Comma-separated local row ids")
    p2.add_argument("--all", action="store_true")
    p2.set_defaults(func=cmd_approve_rewrite)

    p3 = sub.add_parser("rewrite", help="Step 3: Qwen rewrite (DeepInfra from Admin DB)")
    p3.add_argument("--batch-id", required=True)
    p3.add_argument("--limit", type=int, default=0, help="Max topic groups (0=all approved)")
    p3.add_argument("--no-llm", action="store_true")
    p3.set_defaults(func=cmd_rewrite)

    p3b = sub.add_parser("show-rewrites", help="Re-print before/after from manifest")
    p3b.add_argument("--batch-id", required=True)
    p3b.set_defaults(func=cmd_show_rewrites)

    p4 = sub.add_parser("approve-push", help="Step 4: approve rewrites for live push")
    p4.add_argument("--batch-id", required=True)
    p4.add_argument("--names", default=None)
    p4.add_argument("--ids", default=None)
    p4.add_argument("--all", action="store_true")
    p4.set_defaults(func=cmd_approve_push)

    p5 = sub.add_parser("push", help="Step 5: push approved items to Meta + Telnyx")
    p5.add_argument("--batch-id", required=True)
    p5.add_argument("--yes", action="store_true", help="Skip PUSH confirmation")
    p5.add_argument("--sync-remote", action="store_true")
    p5.add_argument("--push-delay", type=float, default=30.0)
    p5.add_argument("--limit", type=int, default=0)
    p5.set_defaults(func=cmd_push)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
