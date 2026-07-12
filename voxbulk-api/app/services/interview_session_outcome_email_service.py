"""Send the correct post-session interview email from a confirmed outcome (never mix thank-you + reschedule)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.career_email_service import CareerEmailService

logger = logging.getLogger(__name__)

TEMPLATE_THANK_YOU = "interview_thank_you"
TEMPLATE_RESCHEDULE = "interview_session_reschedule"
TEMPLATE_OPTED_OUT = "interview_session_opted_out"


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(db: Session, recipient: ServiceOrderRecipient, patch: dict[str, Any]) -> None:
    merged = _loads(recipient.result_json)
    merged.update(patch)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    recipient.updated_at = datetime.utcnow()
    db.add(recipient)
    db.commit()
    db.refresh(recipient)


def _role_company(db: Session, order: ServiceOrder) -> tuple[str, str]:
    from app.services.interview_booking_service import InterviewBookingService
    from app.services.voice_agent_runtime import resolve_voice_call_company_name

    role = "Interview"
    try:
        cfg = json.loads(order.config_json or "{}")
        if isinstance(cfg, dict):
            role = str(cfg.get("role") or cfg.get("position") or order.title or role).strip() or role
            company = str(cfg.get("company_name") or "").strip()
            if company:
                return role, company
    except Exception:
        pass
    company = resolve_voice_call_company_name(
        db, config={}, org_id=order.org_id, order=order
    ) or InterviewBookingService._org_name(db, order)
    return role, company


def dispatch_interview_session_outcome_email(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    outcome: str,
) -> dict[str, Any]:
    """Send exactly one outcome email. Idempotent per outcome family."""
    outcome = str(outcome or "").strip().lower()
    email = str(recipient.email or "").strip().lower()
    if not email or "@" not in email:
        return {"skipped": True, "reason": "no_email"}

    existing = _loads(recipient.result_json)
    role, company = _role_company(db, order)
    first = str(recipient.name or "there").strip().split()[0] or "there"
    name = str(recipient.name or first).strip() or first

    if outcome == "completed":
        if existing.get("thank_you_email_sent_at"):
            return {"skipped": True, "reason": "already_sent", "template_key": TEMPLATE_THANK_YOU}
        # Never send thank-you if a reschedule/opt-out mail already went for this session.
        if existing.get("session_reschedule_email_sent_at") or existing.get("session_opt_out_email_sent_at"):
            return {"skipped": True, "reason": "other_outcome_email_sent"}
        from app.services.interview_missed_call_email_service import maybe_send_interview_thank_you_email

        return maybe_send_interview_thank_you_email(db, order=order, recipient=recipient)

    if outcome == "reschedule":
        if existing.get("session_reschedule_email_sent_at") or existing.get("reschedule_email_sent_at"):
            return {"skipped": True, "reason": "already_sent", "template_key": TEMPLATE_RESCHEDULE}
        from app.services.interview_booking_service import (
            booking_reschedule_url_for_token,
            resolve_booking_url,
        )
        from app.services.interview_early_exit_service import _booking_token

        token = _booking_token(db, order.id, recipient.id)
        token_str = str(token.token) if token else ""
        if not token_str:
            return {"skipped": True, "reason": "no_booking_token"}
        reschedule_url = booking_reschedule_url_for_token(token_str, recipient=recipient)
        booking_url = resolve_booking_url(recipient, token_str)
        ok, err = CareerEmailService.send_templated_critical(
            db,
            template_key=TEMPLATE_RESCHEDULE,
            to_email=email,
            variables={
                "candidate_name": name,
                "first_name": first,
                "role": role,
                "company_name": company,
                "reschedule_url": reschedule_url,
                "booking_url": booking_url,
            },
        )
        patch = {
            "session_reschedule_email_attempted_at": datetime.utcnow().isoformat(),
            "session_reschedule_email_template": TEMPLATE_RESCHEDULE,
            "session_reschedule_email_to": email,
        }
        if ok:
            patch["session_reschedule_email_sent_at"] = datetime.utcnow().isoformat()
            patch["session_reschedule_email_ok"] = True
            patch["reschedule_email_sent_at"] = patch["session_reschedule_email_sent_at"]
            patch["reschedule_email_channel"] = TEMPLATE_RESCHEDULE
        else:
            # Do NOT fall back to interview_booking_reschedule_link / plain text —
            # Admin owns interview_session_reschedule layout; sending another template
            # looks like an "old" email to the candidate.
            patch["session_reschedule_email_ok"] = False
            patch["session_reschedule_email_failed"] = err or "send_failed"
            logger.warning(
                "interview_session_reschedule_send_failed to=%s err=%s",
                email,
                err,
            )
        _save(db, recipient, patch)
        return {"ok": ok, "template_key": TEMPLATE_RESCHEDULE, "error": err}

    if outcome in {"recording_declined", "opted_out"}:
        if existing.get("session_opt_out_email_sent_at"):
            return {"skipped": True, "reason": "already_sent", "template_key": TEMPLATE_OPTED_OUT}
        if outcome == "recording_declined":
            closure_message = (
                "We cannot continue the interview without recording consent for quality and review purposes."
            )
            reason_html = " because recording consent was not given"
        else:
            closure_message = "You asked not to continue with this interview process."
            reason_html = ""
        ok, err = CareerEmailService.send_templated_optional(
            db,
            template_key=TEMPLATE_OPTED_OUT,
            to_email=email,
            variables={
                "candidate_name": name,
                "first_name": first,
                "role": role,
                "company_name": company,
                "closure_message": closure_message,
                "closure_reason_html": reason_html,
            },
        )
        patch = {
            "session_opt_out_email_attempted_at": datetime.utcnow().isoformat(),
            "session_opt_out_email_template": TEMPLATE_OPTED_OUT,
            "session_opt_out_email_to": email,
        }
        if ok:
            patch["session_opt_out_email_sent_at"] = datetime.utcnow().isoformat()
            patch["session_opt_out_email_ok"] = True
        else:
            patch["session_opt_out_email_ok"] = False
            patch["session_opt_out_email_failed"] = err or "send_failed"
        _save(db, recipient, patch)
        return {"ok": ok, "template_key": TEMPLATE_OPTED_OUT, "error": err}

    return {"skipped": True, "reason": f"no_email_for_outcome:{outcome}"}
