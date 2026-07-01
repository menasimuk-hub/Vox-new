#!/usr/bin/env python3
"""Find or deactivate legacy duplicate interview agents (non-canonical slugs).

Usage (from voxbulk-api, project venv):
  python scripts/cleanup_legacy_interview_agents.py --dry-run
  python scripts/cleanup_legacy_interview_agents.py --deactivate
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.agent import AgentDefinition
from app.services.interview_agent_display_service import (
    CANONICAL_INTERVIEW_SLUGS,
    CANONICAL_SLUG_BY_BUCKET,
    _agent_bucket_key,
    filter_canonical_interview_agents,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup legacy duplicate interview agents")
    parser.add_argument("--deactivate", action="store_true", help="Set is_active=false on non-canonical duplicates")
    args = parser.parse_args()
    dry_run = not args.deactivate

    Session = get_sessionmaker()
    db = Session()
    try:
        rows = list(
            db.execute(
                select(AgentDefinition).where(
                    AgentDefinition.is_active.is_(True),
                    AgentDefinition.supports_interview.is_(True),
                )
            ).scalars()
        )
        kept = filter_canonical_interview_agents(rows)
        kept_keys = {row.id or row.slug for row in kept}
        duplicates = [row for row in rows if (row.id or row.slug) not in kept_keys]

        if not duplicates:
            print("OK: no legacy duplicate interview agents found")
            return 0

        print(f"Found {len(duplicates)} legacy duplicate(s) ({len(kept)} canonical kept):")
        for row in duplicates:
            bucket = _agent_bucket_key(row)
            canonical = CANONICAL_SLUG_BY_BUCKET.get(bucket, "(none)")
            print(
                f"  slug={row.slug} id={row.id} name={row.name} "
                f"telnyx={row.telnyx_assistant_id or '(unset)'} bucket={bucket} canonical={canonical}"
            )

        if dry_run:
            print("\nDry run — re-run with --deactivate to deactivate these rows.")
            return 0

        now = datetime.utcnow()
        for row in duplicates:
            if row.slug in CANONICAL_INTERVIEW_SLUGS:
                print(f"  skip canonical slug {row.slug}")
                continue
            row.is_active = False
            row.updated_at = now
            db.add(row)
            print(f"  deactivated slug={row.slug} id={row.id}")
        db.commit()
        print("Done.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
