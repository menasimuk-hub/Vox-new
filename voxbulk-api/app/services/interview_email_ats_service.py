"""Auto ATS when CVs arrive via careers@ email intake."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_ats_billing_service import InterviewAtsBillingError, assert_email_cv_ats_ready
from app.services.interview_ats_service import process_one_ats_recipient, queue_ats_for_recipient
from app.services.interview_cv_exclusion_service import (
    cv_min_ats_score_from_config,
    is_auto_excluded_recipient,
    maybe_reject_recipient_by_ats_threshold,
)

logger = logging.getLogger(__name__)


def _loads_config(order: ServiceOrder) -> dict:
    try:
        cfg = json.loads(order.config_json or "{}")
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _order_ready_for_email_ats(order: ServiceOrder) -> bool:
    cfg = _loads_config(order)
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


def _clear_deferred_email_ats(recipient: ServiceOrderRecipient) -> None:
    try:
        merged = json.loads(recipient.result_json or "{}")
        if not isinstance(merged, dict):
            return
    except Exception:
        return
    if "email_ats_pending_at" not in merged:
        return
    merged.pop("email_ats_pending_at", None)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)


def _has_deferred_email_ats(recipient: ServiceOrderRecipient) -> bool:
    try:
        merged = json.loads(recipient.result_json or "{}")
        if not isinstance(merged, dict) or not merged.get("email_ats_pending_at"):
            return False
    except Exception:
        return False
    status = str(recipient.ats_status or "").lower()
    if status in {"pending", "analyzing"}:
        return True
    if status == "complete" and recipient.ats_score is not None:
        return False
    if status == "failed":
        return False
    return True


def retry_deferred_email_ats(
    db: Session,
    *,
    order_id: str | None = None,
    limit: int = 10,
) -> int:
    """Re-run ATS for emailed CVs that were deferred until role/criteria were saved."""
    from sqlalchemy import select

    from app.models.service_order import ServiceOrder, ServiceOrderRecipient

    query = (
        select(ServiceOrderRecipient, ServiceOrder)
        .join(ServiceOrder, ServiceOrder.id == ServiceOrderRecipient.order_id)
        .where(ServiceOrder.service_code == "interview")
        .order_by(ServiceOrderRecipient.created_at.asc())
    )
    if order_id:
        query = query.where(ServiceOrder.id == order_id)
    rows = list(db.execute(query.limit(max(1, limit * 4))).all())
    processed = 0
    for recipient, order in rows:
        if processed >= limit:
            break
        if not _has_deferred_email_ats(recipient):
            continue
        if not _order_ready_for_email_ats(order):
            continue
        result = auto_ats_for_cv_recipient(db, order, recipient)
        if result.get("ok"):
            _clear_deferred_email_ats(recipient)
            db.add(recipient)
            db.commit()
            processed += 1
            continue
        if result.get("reason") == "criteria_not_ready":
            continue
        if str(recipient.ats_status or "").lower() in {"pending", "analyzing", "complete"}:
            _clear_deferred_email_ats(recipient)
            db.add(recipient)
            db.commit()
            processed += 1
    return processed


def auto_ats_for_cv_recipient(
    db: Session,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    *,
    is_update: bool = False,
) -> dict[str, object]:
    """Run ATS on an accepted CV; reject below threshold before AI screening usage is recorded."""
    if is_auto_excluded_recipient(recipient):
        return {"ok": False, "reason": "auto_excluded"}

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
        assert_email_cv_ats_ready(order)
    except InterviewAtsBillingError as exc:
        _mark_ats_pending(recipient)
        db.add(recipient)
        db.commit()
        return {"ok": False, "reason": "criteria_not_ready", "error": str(exc)}

    min_score = cv_min_ats_score_from_config(_loads_config(order))

    try:
        queue_ats_for_recipient(db, recipient, order=order, force=bool(is_update))
        db.commit()
        db.refresh(recipient)
        if str(recipient.ats_status or "").lower() in {"pending", "analyzing"}:
            process_one_ats_recipient(db, recipient)
            db.refresh(recipient)
    except Exception:
        logger.exception(
            "email_cv_ats_failed",
            extra={"order_id": order.id, "recipient_id": recipient.id},
        )
        return {"ok": False, "reason": "ats_failed"}

    if str(recipient.ats_status or "").lower() != "complete" or recipient.ats_score is None:
        return {"ok": False, "reason": "ats_failed", "ats_status": recipient.ats_status}

    _clear_deferred_email_ats(recipient)
    db.add(recipient)
    actual_score = int(recipient.ats_score)
    if maybe_reject_recipient_by_ats_threshold(db, order, recipient):
        return {
            "ok": False,
            "reason": "ats_below_threshold",
            "min_score": min_score,
            "actual_score": actual_score,
        }

    try:
        from app.services.interview_ats_billing_service import record_ats_charge

        record_ats_charge(db, order, org, recipient, source="auto")
    except Exception:
        logger.exception(
            "email_cv_ats_charge_failed",
            extra={"order_id": order.id, "recipient_id": recipient.id},
        )
        return {"ok": False, "reason": "charge_failed"}

    return {"ok": True, "min_score": min_score, "actual_score": actual_score}


auto_ats_after_email_cv = auto_ats_for_cv_recipient
