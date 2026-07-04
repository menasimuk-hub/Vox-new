"""Retire superseded WA survey templates after Meta approves the successor clone."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateService

logger = logging.getLogger(__name__)

_LOCAL_ID_PREFIX = "local-"


def process_one_superseded_template_deletion(db: Session) -> dict[str, Any]:
    """Delete at most one old Meta template whose successor clone is APPROVED."""
    rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate)
            .where(
                TelnyxWhatsappTemplate.parent_template_id.isnot(None),
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
            )
            .order_by(TelnyxWhatsappTemplate.updated_at.asc())
        ).scalars().all()
    )
    for successor in rows:
        parent_id = int(successor.parent_template_id or 0)
        if not parent_id:
            continue
        if str(successor.status or "").upper() != "APPROVED":
            continue
        parent = db.get(TelnyxWhatsappTemplate, parent_id)
        if parent is None:
            successor.parent_template_id = None
            db.add(successor)
            db.commit()
            return {"ok": True, "action": "cleared_orphan_parent_ref", "successor_id": successor.id}
        if parent.active_for_survey:
            continue

        parent_name = str(parent.name or "").strip()
        record_id = str(parent.telnyx_record_id or "").strip()
        deleted_remote = False
        if parent_name and record_id and not record_id.startswith(_LOCAL_ID_PREFIX):
            try:
                MetaWhatsappTemplateService.delete_message_template(db, name=parent_name)
                deleted_remote = True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "superseded_template_meta_delete_failed",
                    extra={"parent_id": parent.id, "name": parent_name, "error": str(exc)},
                )
                return {
                    "ok": False,
                    "action": "meta_delete_failed",
                    "parent_id": parent.id,
                    "successor_id": successor.id,
                    "error": str(exc)[:300],
                }

        from app.services.telnyx_whatsapp_template_sync_service import _detach_template_references

        _detach_template_references(db, int(parent.id))
        db.delete(parent)
        successor.parent_template_id = None
        db.add(successor)
        db.commit()
        return {
            "ok": True,
            "action": "deleted_superseded",
            "deleted_parent_id": parent_id,
            "deleted_parent_name": parent_name,
            "successor_id": successor.id,
            "deleted_remote": deleted_remote,
        }

    return {"ok": True, "action": "none_pending"}


def refresh_successor_status_from_meta(db: Session, row: TelnyxWhatsappTemplate) -> None:
    """After webhook/status refresh, attempt superseded cleanup if newly APPROVED."""
    if str(row.status or "").upper() != "APPROVED":
        return
    if not row.parent_template_id:
        return
    process_one_superseded_template_deletion(db)
