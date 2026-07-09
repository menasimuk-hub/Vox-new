#!/usr/bin/env python3
"""Script 2 — Test Qwen utility rewrite on approved MARKETING templates (no push).

Workflow:
  1. Run list_marketing_wa_templates.py first (creates batch manifest).
  2. This script approves templates for rewrite, runs Qwen via DeepInfra (Admin DB), shows before/after.

Does NOT push to Meta/Telnyx. Use purge_marketing_wa_templates.py push after you approve.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python scripts/test_marketing_wa_utility_rewrite.py --batch-id 20260709 --limit 1
  .venv/bin/python scripts/test_marketing_wa_utility_rewrite.py --batch-id 20260709 --names was_hotel_* --limit 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import get_sessionmaker
from app.services.survey_wa_utility_rewrite_service import resolve_utility_llm_config
from app.services.wa_marketing_review_service import (
    approve_manifest_items,
    load_manifest,
    print_rewritten_templates,
    run_batch_rewrites,
)


def _parse_names(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


def _parse_ids(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Qwen MARKETING→UTILITY rewrite (no push)")
    parser.add_argument("--batch-id", required=True, help="Batch from list_marketing_wa_templates.py")
    parser.add_argument("--limit", type=int, default=1, help="Max topic groups to rewrite (default: 1)")
    parser.add_argument("--names", default=None, help="Comma-separated template names/prefix* to approve")
    parser.add_argument("--ids", default=None, help="Comma-separated local row ids to approve")
    parser.add_argument("--all", action="store_true", help="Approve all listed templates for rewrite")
    parser.add_argument("--no-llm", action="store_true", help="Rule-based only (not recommended)")
    parser.add_argument("--skip-approve", action="store_true", help="Skip approve step (items already approved_rewrite)")
    args = parser.parse_args()

    batch_id = str(args.batch_id).strip()
    if not args.skip_approve:
        if not args.all and not args.names and not args.ids:
            print("Approving --limit templates by name filter (use --all for everything, --names for filter)", file=sys.stderr)
            if args.limit and args.limit > 0:
                manifest = load_manifest(batch_id)
                names_to_approve: list[str] = []
                count = 0
                for group in manifest.get("groups") or []:
                    for item in group.get("items") or []:
                        if str(item.get("status")) != "listed":
                            continue
                        names_to_approve.append(str(item.get("remote_name") or item.get("label")))
                        count += 1
                        if count >= args.limit:
                            break
                    if count >= args.limit:
                        break
                args.names = ",".join(names_to_approve) if names_to_approve else None
            else:
                args.all = True

        result = approve_manifest_items(
            batch_id,
            names=_parse_names(args.names),
            ids=_parse_ids(args.ids),
            approve_all=bool(args.all),
            from_status="listed",
            to_status="approved_rewrite",
        )
        print(f"Approved {result.get('approved', 0)} template(s) for rewrite.")

    db = get_sessionmaker()()
    try:
        llm_cfg = resolve_utility_llm_config(db)
        print(f"DeepInfra: {llm_cfg['base_url']} | model: {llm_cfg['model']}")
        result = run_batch_rewrites(
            db,
            batch_id=batch_id,
            use_llm=not args.no_llm,
            limit_groups=args.limit or 0,
        )
        manifest = load_manifest(batch_id)
    finally:
        db.close()

    print(f"Rewrote {result.get('rewritten', 0)} template(s).")
    print("")
    print_rewritten_templates(manifest)
    print("")
    print("When happy, approve push then push live:")
    print(f"  .venv/bin/python scripts/purge_marketing_wa_templates.py approve-push --batch-id {batch_id} --all")
    print(f"  .venv/bin/python scripts/purge_marketing_wa_templates.py push --batch-id {batch_id} --yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
