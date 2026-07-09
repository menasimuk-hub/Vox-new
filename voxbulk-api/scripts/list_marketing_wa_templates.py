#!/usr/bin/env python3
"""Script 1 — List all MARKETING templates on Meta (+447822002099) and Telnyx (+447822002055).

Read-only. No LLM. No DB writes. Saves a batch manifest for script 2.

Usage (VPS):
  cd /www/voxbulk/voxbulk-api
  .venv/bin/python scripts/list_marketing_wa_templates.py
  .venv/bin/python scripts/list_marketing_wa_templates.py --batch-id 20260709 --limit 10
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
from app.services.wa_marketing_review_service import (
    create_marketing_list_manifest,
    print_listed_templates,
    review_batch_dir,
)


def _default_batch_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def main() -> int:
    parser = argparse.ArgumentParser(description="List MARKETING WA templates (Meta + Telnyx)")
    parser.add_argument("--batch-id", default=None, help=f"Batch folder (default: {_default_batch_id()})")
    parser.add_argument("--limit", type=int, default=0, help="Max templates (0=all)")
    parser.add_argument("--name-contains", default=None)
    args = parser.parse_args()

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

    print(f"DeepInfra: OK (Admin DB) | rewrite model: {llm_cfg['model']}")
    print("")
    print_listed_templates(manifest)
    print(f"Manifest: {review_batch_dir(batch_id)}/manifest.json")
    print("")
    print("Script 2 — test rewrite on approved templates:")
    print(f"  .venv/bin/python scripts/test_marketing_wa_utility_rewrite.py --batch-id {batch_id} --limit 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
