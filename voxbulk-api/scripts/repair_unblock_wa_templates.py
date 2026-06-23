#!/usr/bin/env python3
"""One-time repair: re-enable WA survey/feedback types and templates disabled by the hide/blocklist rollout.

Also runs automatically on API startup after the rollback deploy.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.services.wa_template_unblock_repair_service import repair_unblocked_wa_templates


def repair(*, dry_run: bool) -> dict:
    settings = get_settings()
    with get_sessionmaker()() as db:
        stats = repair_unblocked_wa_templates(db, dry_run=dry_run)
    stats["database"] = settings.database_url[:64] + "…"
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-enable WA survey/feedback catalog rows disabled by the blocklist rollout",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing")
    args = parser.parse_args()

    url = str(get_settings().database_url or "")
    if url.startswith("sqlite:"):
        print(f"WARNING: using SQLite ({url}) — ensure this is intentional", file=sys.stderr)

    result = repair(dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
