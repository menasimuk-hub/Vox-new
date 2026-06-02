"""Auto ATS when CVs arrive via careers@ email intake."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_ats_billing_service import InterviewAtsBillingError, charge_and_queue_ats

logger = logging.getLogger(__name__)


def _order_ready_for_email_ats(order: ServiceOrder) -> bool:
    try:
        cfg = json.loads(order.config_json or "{}")
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
    role = str(cfg.get("role") or cfg.get("position") or order.title or "").strip()
    criteria = str(cfg.get("criteria") or cfg.get("screening_criteria") or "").strip()
    return bool(role and criteria)


def _mark_ats_pending(recipient: ServiceOrderRecipient) -> None:
    try:
        merged = json.loads(recipient.result_json or "{}")
        if not isinstance(merged, dict):
            merged = {}
    except Exception:
        merged = {}
    merged["email_ats_pending_at"] = datetime.utcnow().isoformat()
    recipient.result_json = json.dumps(merged, ensure_ascii=False)


def auto_ats_for_cv_recipient(
    db: Session,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    *,
    is_update: bool = False,
) -> dict[str, object]:
    """Queue paid ATS when a CV arrives by email or manual upload."""
    org = db.get(Organisation, order.org_id)
    if org is None:
        return {"ok": False, "reason": "no_org"}

    if not _order_ready_for_email_ats(order):
        _mark_ats_pending(recipient)
        db.add(recipient)
        db.commit()
        logger.info(
            "email_cv_ats_deferred",
            extra={"order_id": order.id, "recipient_id": recipient.id},
        )
        return {"ok": False, "reason": "criteria_not_ready", "deferred": True}

    try:
        result = charge_and_queue_ats(
            db,
            order,
            org,
            confirm_charge=True,
            recipient_ids=[recipient.id],
            force=bool(is_update),
            require_script=False,
        )
        return {"ok": True, **result}
    except InterviewAtsBillingError as exc:
        _mark_ats_pending(recipient)
        db.add(recipient)
        db.commit()
        logger.warning(
            "email_cv_ats_billing_blocked",
            extra={"order_id": order.id, "recipient_id": recipient.id, "error": str(exc)},
        )
        return {"ok": False, "reason": "billing", "error": str(exc)}


auto_ats_after_email_cv = auto_ats_for_cv_recipient
