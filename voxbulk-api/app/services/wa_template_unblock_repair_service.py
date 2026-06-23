"""Re-enable WA survey/feedback rows disabled by the hide/blocklist rollout."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import inspect, select, text

from app.models.customer_feedback import FeedbackSurveyType, FeedbackWaTemplate
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

_BLOCKLIST_FILE = (
    Path(__file__).resolve().parents[2] / "seed-data" / "wa-templates" / "export-template-names.txt"
)


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

    linked_template_ids = {
        int(tid)
        for tid in db.execute(select(SurveyTypeTemplate.template_id).distinct()).scalars()
        if tid is not None
    }
    for row in rows:
        rid = int(row.id)
        if rid in unblock_ids:
            continue
        if rid in linked_template_ids:
            unblock_ids.add(rid)
        elif str(row.survey_type_id or "").strip():
            unblock_ids.add(rid)

    return unblock_ids


def repair_unblocked_wa_templates(db, *, dry_run: bool = False) -> dict:
    """Idempotent repair after hide/blocklist rollback. Safe to run on every API startup."""
    now = datetime.utcnow()
    stats = {
        "dry_run": dry_run,
        "blocklist_size": len(blocked_meta_template_names()),
        "survey_types_reactivated": 0,
        "feedback_survey_types_reactivated": 0,
        "optional_flags_cleared": {},
        "telnyx_templates_reactivated": 0,
        "feedback_templates_reactivated": 0,
    }

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
