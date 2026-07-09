#!/usr/bin/env python3
"""One script: migrate ALL MARKETING WA templates → UTILITY (all languages, one run).

Uses DeepInfra multilingual models (Qwen 32B → Mistral Small 3.2 → Qwen 72B), with DeepSeek
fallback. API keys from Admin → Integrations (not .env). Pushes to Meta 99 + Telnyx 55.

Usage (VPS — from /www/voxbulk/voxbulk-api):

  # 1) Review only — list + rewrite ALL marketing templates, print before/after
  .venv/bin/python scripts/migrate_marketing_to_utility.py

  # 2) Same with explicit batch id (re-runnable)
  .venv/bin/python scripts/migrate_marketing_to_utility.py --batch-id 20260709

  # 3) Filter one industry/prefix
  .venv/bin/python scripts/migrate_marketing_to_utility.py --name-contains cfs_hotel

  # 4) Push live after you reviewed output (lint_ok items only)
  .venv/bin/python scripts/migrate_marketing_to_utility.py --batch-id 20260709 --push --yes

Review files: seed-data/wa-survey/migration-reports/marketing-utility-review/BATCH/
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
from app.services.survey_wa_utility_rewrite_service import (
    DEEPINFRA_UTILITY_MODELS,
    resolve_utility_llm_config,
)
from app.services.wa_marketing_review_service import run_full_marketing_migration


def _default_batch_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate ALL MARKETING WA templates to UTILITY (one script, all languages)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--batch-id", default=None, help=f"Batch folder (default: today {_default_batch_id()})")
    parser.add_argument("--name-contains", default=None, help="Filter remote names (e.g. cfs_hotel, was_employee_)")
    parser.add_argument("--limit", type=int, default=0, help="Max templates to list (0 = all actionable)")
    parser.add_argument("--no-llm", action="store_true", help="Rule-based rewrite only (not recommended)")
    parser.add_argument("--push", action="store_true", help="After rewrite, approve lint_ok items and push live")
    parser.add_argument("--yes", action="store_true", help="With --push: skip confirmation and push immediately")
    parser.add_argument("--include-lint-failures", action="store_true", help="With --push: also push lint-failed rows")
    parser.add_argument("--push-delay", type=float, default=30.0, help="Seconds between Meta/Telnyx pushes")
    parser.add_argument("--sync-remote", action="store_true", help="Pull remote status after each push")
    args = parser.parse_args()

    batch_id = str(args.batch_id or _default_batch_id()).strip()
    db = get_sessionmaker()()
    try:
        llm_cfg = resolve_utility_llm_config(db)
        print("LLM provider:", llm_cfg.get("provider"), "| model:", llm_cfg.get("model"))
        print("DeepInfra model chain:", ", ".join(DEEPINFRA_UTILITY_MODELS))
        print("Base URL:", llm_cfg.get("base_url"))
        print("")
        result = run_full_marketing_migration(
            db,
            batch_id=batch_id,
            name_contains=args.name_contains,
            limit=args.limit or 0,
            use_llm=not args.no_llm,
            push=bool(args.push),
            push_yes=bool(args.yes),
            push_delay=args.push_delay,
            sync_remote=bool(args.sync_remote),
            only_lint_ok_push=not args.include_lint_failures,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    if args.push and result.get("push"):
        push = result["push"]
        if push.get("message"):
            print(push["message"])
        else:
            print(f"PUSH done: {push.get('ok', 0)} ok, {push.get('failed', 0)} failed")
            if int(push.get("failed") or 0) > 0:
                return 1
    elif not args.push:
        print("Review complete. To push lint_ok items:")
        print(f"  .venv/bin/python scripts/migrate_marketing_to_utility.py --batch-id {batch_id} --push --yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
