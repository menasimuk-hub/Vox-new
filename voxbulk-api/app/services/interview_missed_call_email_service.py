"""Missed / no-answer interview follow-up email — agent-configured template per service."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import AgentDefinition
from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.career_email_service import CareerEmailService
from app.services.interview_booking_service import resolve_booking_url
from app.services.survey_dispatch_service import _first_name
from app.services.voice_agent_runtime import resolve_voice_call_company_name

logger = logging.getLogger(__name__)

DEFAULT_INTERVIEW_MISSED_CALL_TEMPLATE = "interview_missed_call_followup"
DEFAULT_FOLLOWUP_MESSAGE = (
    "Please use the link below to choose a time when we can call you back for your short AI phone interview."
)


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    return _loads(order.config_json)


def resolve_missed_call_email_template_key(
    agent: AgentDefinition | None,
    *,
    service_key: str = "interview",
) -> str | None:
    """Return configured template key, or None when follow-up email is disabled for this agent."""
    if agent is None:
        return DEFAULT_INTERVIEW_MISSED_CALL_TEMPLATE
    if service_key == "survey":
        key = str(getattr(agent, "missed_call_email_template_survey", None) or "").strip().lower()
    else:
        key = str(getattr(agent, "missed_call_email_template_interview", None) or "").strip().lower()
    if key in {"none", "disabled", "off"}:
        return None
    if not key:
        return DEFAULT_INTERVIEW_MISSED_CALL_TEMPLATE
    return key


def resolve_missed_call_experience_notes(agent: AgentDefinition | None, *, service_key: str = "interview") -> str:
    if agent is None or service_key != "interview":
        return ""
    notes = str(getattr(agent, "missed_call_followup_notes_interview", None) or "").strip()
    if notes:
        return notes
    return str(getattr(agent, "retry_policy_notes", None) or "").strip()


def should_send_missed_call_followup_email(
    *,
    terminal_status: str,
    voicemail_detected: bool,
    voicemail_behavior: str | None,
) -> tuple[bool, str | None]:
    """Respect agent voicemail policy — only send on hang-up-for-now path when VM was detected."""
    status = str(terminal_status or "").lower()
    if status not in {"no_answer", "busy"}:
        return False, "not_missed_terminal"
    if voicemail_detected:
        behavior = str(voicemail_behavior or "hang_up").strip().lower()
        if behavior == "leave_message":
            return False, "voicemail_message_left"
        if behavior == "retry_later":
            return False, "retry_scheduled"
        if behavior != "hang_up":
            return False, f"unsupported_voicemail_behavior:{behavior}"
    return True, None


def _resolve_recipient_booking_url(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> str:
    parsed = _loads(recipient.result_json)
    stored = str(parsed.get("booking_url") or "").strip()
    if stored:
        return stored
    token_row = db.execute(
        select(InterviewBookingToken).where(
            InterviewBookingToken.order_id == order.id,
            InterviewBookingToken.recipient_id == recipient.id,
        )
    ).scalar_one_or_none()
    if token_row is not None:
        return resolve_booking_url(recipient, token_row.token)
    return ""


def build_missed_call_email_variables(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    agent: AgentDefinition | None,
) -> dict[str, str]:
    config = _order_config(order)
    role = str(config.get("role") or order.title or "the role").strip()
    company_name = resolve_voice_call_company_name(db, config=config, org_id=order.org_id, order=order)
    first = _first_name(recipient.name or "there")
    booking_url = _resolve_recipient_booking_url(db, order, recipient)
    notes = resolve_missed_call_experience_notes(agent, service_key="interview")
    followup_message = notes or DEFAULT_FOLLOWUP_MESSAGE
    return {
        "candidate_name": recipient.name or first or "there",
        "first_name": first,
        "role": role,
        "company_name": company_name,
        "booking_url": booking_url,
        "followup_message": followup_message,
        "org_name": company_name,
    }


def maybe_send_interview_missed_call_email(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    agent: AgentDefinition | None,
    terminal_status: str,
    voicemail_detected: bool = False,
    voicemail_behavior: str | None = None,
) -> dict[str, Any]:
    """
    Send agent-configured missed-call follow-up email (idempotent).

    Returns summary dict stored on recipient result_json under missed_call_email.
    """
    if str(recipient.status or "").lower() == "opted_out":
        return {"skipped": True, "reason": "opted_out"}

    outreach = str(recipient.email or "").strip()
    if not outreach:
        return {"skipped": True, "reason": "no_email"}

    existing = _loads(recipient.result_json)
    if existing.get("missed_call_email_sent_at"):
        return {
            "skipped": True,
            "reason": "already_sent",
            "sent_at": existing.get("missed_call_email_sent_at"),
            "template_key": existing.get("missed_call_email_template"),
            "ok": existing.get("missed_call_email_ok"),
        }

    should_send, skip_reason = should_send_missed_call_followup_email(
        terminal_status=terminal_status,
        voicemail_detected=voicemail_detected,
        voicemail_behavior=voicemail_behavior,
    )
    if not should_send:
        payload = {
            "missed_call_email_skipped_at": datetime.utcnow().isoformat(),
            "missed_call_email_skip_reason": skip_reason,
            "missed_call_voicemail_behavior": voicemail_behavior,
        }
        merged = dict(existing)
        merged.update(payload)
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        logger.info(
            "interview_missed_call_email_skipped",
            extra={
                "order_id": order.id,
                "recipient_id": recipient.id,
                "reason": skip_reason,
                "terminal_status": terminal_status,
            },
        )
        return {"skipped": True, "reason": skip_reason}

    template_key = resolve_missed_call_email_template_key(agent, service_key="interview")
    if not template_key:
        payload = {
            "missed_call_email_skipped_at": datetime.utcnow().isoformat(),
            "missed_call_email_skip_reason": "template_disabled",
        }
        merged = dict(existing)
        merged.update(payload)
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        return {"skipped": True, "reason": "template_disabled"}

    variables = build_missed_call_email_variables(db, order=order, recipient=recipient, agent=agent)
    if not str(variables.get("booking_url") or "").strip():
        payload = {
            "missed_call_email_failed": "booking_url_missing",
            "missed_call_email_attempted_at": datetime.utcnow().isoformat(),
            "missed_call_email_template": template_key,
        }
        merged = dict(existing)
        merged.update(payload)
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        logger.warning(
            "interview_missed_call_email_failed",
            extra={"order_id": order.id, "recipient_id": recipient.id, "error": "booking_url_missing"},
        )
        return {"ok": False, "error": "booking_url_missing", "template_key": template_key}

    attempted_at = datetime.utcnow().isoformat()
    sent_ok, err = CareerEmailService.send_templated_optional(
        db,
        template_key=template_key,
        to_email=outreach,
        variables=variables,
    )
    merged = dict(existing)
    merged.update(
        {
            "missed_call_email_attempted_at": attempted_at,
            "missed_call_email_template": template_key,
            "missed_call_email_to": outreach.lower(),
            "missed_call_voicemail_behavior": voicemail_behavior,
            "missed_call_terminal_status": terminal_status,
            "missed_call_voicemail_detected": bool(voicemail_detected),
            "missed_call_experience_notes": resolve_missed_call_experience_notes(agent),
        }
    )
    if sent_ok:
        merged["missed_call_email_ok"] = True
        merged["missed_call_email_sent_at"] = datetime.utcnow().isoformat()
        merged.pop("missed_call_email_failed", None)
        logger.info(
            "interview_missed_call_email_sent",
            extra={
                "order_id": order.id,
                "recipient_id": recipient.id,
                "template_key": template_key,
                "to": outreach,
            },
        )
    else:
        merged["missed_call_email_ok"] = False
        merged["missed_call_email_failed"] = err or "send_failed"
        logger.warning(
            "interview_missed_call_email_failed",
            extra={
                "order_id": order.id,
                "recipient_id": recipient.id,
                "template_key": template_key,
                "error": err,
            },
        )
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
    return {
        "ok": sent_ok,
        "error": err,
        "template_key": template_key,
        "sent_at": merged.get("missed_call_email_sent_at"),
    }


def missed_call_email_report_payload(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    parsed: dict[str, Any],
) -> dict[str, Any]:
    config = _order_config(order)
    agent = None
    try:
        from app.services.interview_voice_agent_service import resolve_interview_agent_for_order

        agent = resolve_interview_agent_for_order(db, order, config)
    except Exception:
        agent = None

    status = str(recipient.status or parsed.get("terminal_status") or "pending").lower()
    email_block: dict[str, Any] = {
        "template_key": parsed.get("missed_call_email_template"),
        "sent_at": parsed.get("missed_call_email_sent_at"),
        "attempted_at": parsed.get("missed_call_email_attempted_at"),
        "ok": parsed.get("missed_call_email_ok"),
        "failed": parsed.get("missed_call_email_failed"),
        "skipped_reason": parsed.get("missed_call_email_skip_reason"),
        "to": parsed.get("missed_call_email_to"),
    }
    if parsed.get("missed_call_email_sent_at") and parsed.get("missed_call_email_ok"):
        email_block["outcome_label"] = "Follow-up email sent"
    elif parsed.get("missed_call_email_failed"):
        email_block["outcome_label"] = f"Follow-up email failed — {parsed.get('missed_call_email_failed')}"
    elif parsed.get("missed_call_email_skip_reason"):
        reason = str(parsed.get("missed_call_email_skip_reason"))
        labels = {
            "voicemail_message_left": "No email — voicemail message left",
            "retry_scheduled": "No email — marked for call retry",
            "template_disabled": "Follow-up email disabled on agent",
            "no_email": "No candidate email on file",
            "not_missed_terminal": "Not a missed-call outcome",
        }
        email_block["outcome_label"] = labels.get(reason, f"No follow-up email ({reason})")
    else:
        email_block["outcome_label"] = "No follow-up email sent"

    behavior = parsed.get("missed_call_voicemail_behavior") or (getattr(agent, "voicemail_behavior", None) if agent else None)
    behavior_labels = {
        "hang_up": "Hang up for now",
        "leave_message": "Leave voicemail message",
        "retry_later": "Mark for retry",
    }
    status_labels = {
        "no_answer": "No answer",
        "busy": "Busy",
        "completed": "Completed",
        "failed": "Call failed",
        "opted_out": "Opted out",
        "cancelled": "Cancelled",
        "skipped": "Skipped",
    }
    terminal = str(parsed.get("terminal_status") or parsed.get("missed_call_terminal_status") or status or "").lower()
    return {
        "status": status,
        "status_label": status_labels.get(status, status.replace("_", " ").title() if status else "—"),
        "terminal_status": terminal or None,
        "terminal_status_label": status_labels.get(terminal, terminal.replace("_", " ").title() if terminal else "—"),
        "voicemail_detected": bool(parsed.get("voicemail_detected") or parsed.get("missed_call_voicemail_detected")),
        "voicemail_behavior": behavior,
        "voicemail_behavior_label": behavior_labels.get(str(behavior or "").lower(), behavior or "—"),
        "hangup_cause": parsed.get("hangup_cause"),
        "missed_call_email": email_block,
        "experience_notes": str(parsed.get("missed_call_experience_notes") or resolve_missed_call_experience_notes(agent)).strip(),
    }


def maybe_send_interview_meeting_missed_email(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
) -> dict[str, Any]:
    """Email when a candidate misses a booked online meeting slot (not PSTN missed-call flow)."""
    outreach = str(recipient.email or "").strip()
    if not outreach:
        return {"skipped": True, "reason": "no_email"}

    existing = _loads(recipient.result_json)
    if existing.get("meeting_missed_email_sent_at"):
        return {"skipped": True, "reason": "already_sent"}

    config = _order_config(order)
    role = str(config.get("role") or order.title or "the role").strip()
    company_name = resolve_voice_call_company_name(db, config=config, org_id=order.org_id, order=order)
    booking_url = _resolve_recipient_booking_url(db, order, recipient)
    if not booking_url:
        return {"skipped": True, "reason": "booking_url_missing"}

    sent_ok, err = CareerEmailService.send_templated_optional(
        db,
        template_key="interview_meeting_missed",
        to_email=outreach,
        variables={
            "candidate_name": recipient.name or "there",
            "role": role,
            "company_name": company_name,
            "booking_url": booking_url,
        },
    )
    merged = dict(existing)
    if sent_ok:
        merged["meeting_missed_email_sent_at"] = datetime.utcnow().isoformat()
        merged.pop("meeting_missed_email_failed", None)
    else:
        merged["meeting_missed_email_failed"] = err or "send_failed"
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
    return {"ok": sent_ok, "error": err}
