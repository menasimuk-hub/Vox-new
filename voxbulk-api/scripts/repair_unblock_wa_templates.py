#!/usr/bin/env python3
"""One-time repair: re-enable WA survey/feedback types and templates disabled by the hide/blocklist rollout.

Run on VPS after deploying the rollback revert:

  cd /www/voxbulk/voxbulk-api
  source .venv/bin/activate
  python scripts/repair_unblock_wa_templates.py --dry-run
  python scripts/repair_unblock_wa_templates.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import inspect, select, text

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))
os.chdir(API_ROOT)

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackSurveyType, FeedbackWaTemplate
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

_BLOCKLIST_FILE = API_ROOT / "seed-data" / "wa-templates" / "export-template-names.txt"


@lru_cache(maxsize=1)
def blocked_meta_template_names() -> frozenset[str]:
    names: set[str] = set()
    if _BLOCKLIST_FILE.is_file():
        for line in _BLOCKLIST_FILE.read_text(encoding="utf-8").splitlines():
            clean = line.strip().lower()
            if clean and not clean.startswith("#"):
                names.add(clean)
    return frozenset(names)


def _table_has_column(db, table: str, column: str) -> bool:
    try:
        insp = inspect(db.get_bind())
        return column in {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return False


def _clear_optional_flags(db, *, dry_run: bool) -> dict[str, int]:
    """Clear hide/blocklist columns that may exist in DB but not in reverted ORM models."""
    cleared: dict[str, int] = {}
    updates = [
        ("survey_types", "customer_hidden", "system_template_kind IS NULL"),
        ("survey_types", "wa_platform_block_exempt", "system_template_kind IS NULL"),
        ("feedback_survey_types", "customer_hidden", "archived_at IS NULL"),
        ("feedback_survey_types", "wa_platform_block_exempt", "archived_at IS NULL"),
    ]
    for table, column, where in updates:
        if not _table_has_column(db, table, column):
            continue
        count = db.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {column} = 1 AND {where}")
        ).scalar_one()
        cleared[f"{table}.{column}"] = int(count or 0)
        if not dry_run and count:
            db.execute(text(f"UPDATE {table} SET {column} = 0 WHERE {column} = 1 AND {where}"))
    return cleared


def _collect_telnyx_unblock_ids(db) -> set[int]:
    names = blocked_meta_template_names()
    rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars().all())
    unblock_ids: set[int] = set()
    matched_names: set[str] = set()

    for row in rows:
        name = str(row.name or "").strip().lower()
        if name in names:
            unblock_ids.add(int(row.id))
            matched_names.add(name)

    changed = True
    while changed:
        changed = False
        for row in rows:
            rid = int(row.id)
            if rid in unblock_ids:
                continue
            name = str(row.name or "").strip().lower()
            parent_id = getattr(row, "parent_template_id", None)
            if name in matched_names or (parent_id is not None and int(parent_id) in unblock_ids):
                unblock_ids.add(rid)
                if name:
                    matched_names.add(name)
                changed = True

    return unblock_ids


def repair(*, dry_run: bool) -> dict:
    settings = get_settings()
    now = datetime.utcnow()
    stats = {
        "dry_run": dry_run,
        "database": settings.database_url[:64] + "…",
        "blocklist_size": len(blocked_meta_template_names()),
        "survey_types_reactivated": 0,
        "feedback_survey_types_reactivated": 0,
        "optional_flags_cleared": {},
        "telnyx_templates_reactivated": 0,
        "feedback_templates_reactivated": 0,
    }

    with get_sessionmaker()() as db:
        for row in db.execute(
            select(SurveyType).where(SurveyType.system_template_kind.is_(None))
        ).scalars():
            if row.is_active:
                continue
            stats["survey_types_reactivated"] += 1
            if not dry_run:
                row.is_active = True
                row.updated_at = now
                db.add(row)

        for row in db.execute(
            select(FeedbackSurveyType).where(FeedbackSurveyType.archived_at.is_(None))
        ).scalars():
            if row.is_active:
                continue
            stats["feedback_survey_types_reactivated"] += 1
            if not dry_run:
                row.is_active = True
                row.updated_at = now
                db.add(row)

        stats["optional_flags_cleared"] = _clear_optional_flags(db, dry_run=dry_run)

        telnyx_ids = _collect_telnyx_unblock_ids(db)
        for row in db.execute(select(TelnyxWhatsappTemplate)).scalars():
            if int(row.id) not in telnyx_ids:
                continue
            if row.active_for_survey:
                continue
            stats["telnyx_templates_reactivated"] += 1
            if not dry_run:
                row.active_for_survey = True
                row.updated_at = now
                db.add(row)

        for row in db.execute(select(FeedbackWaTemplate)).scalars():
            if row.is_active:
                continue
            stats["feedback_templates_reactivated"] += 1
            if not dry_run:
                row.is_active = True
                row.updated_at = now
                db.add(row)

        if not dry_run:
            db.commit()

    stats["ok"] = True
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
