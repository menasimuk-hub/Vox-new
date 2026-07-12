"""Schedule and dispatch AI voice follow-up for unhappy WA Survey respondents."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_ai_follow_up_job import SurveyAiFollowUpJob
from app.services.customer_feedback.feedback_ai_followup_service import (
    FOLLOWUP_TERMINAL,
    FollowUpDefer,
    FollowUpSkip,
    LOW_ANSWERS,
    _build_followup_instructions,
    _job_outcome,
    _next_calling_window_utc,
    _pre_dial_billing_allowed,
    _resolve_followback_assistant,
    _set_job_outcome,
    _settle_followup_call_billing,
    resolve_followup_delay_hours,
)
from app.utils.ofcom import now_uk, org_calling_allowed

logger = logging.getLogger(__name__)


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        raw = json.loads(order.config_json or "{}")
        return raw if isinstance(raw, dict) else {}
    except json.JSONDecodeError:
        return {}


def load_ai_follow_up_from_order(order: ServiceOrder) -> dict[str, Any]:
    cfg = _order_config(order).get("ai_follow_up")
    return cfg if isinstance(cfg, dict) else {}


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        raw = json.loads(recipient.result_json or "{}")
        return raw if isinstance(raw, dict) else {}
    except json.JSONDecodeError:
        return {}


def _wa_answers(recipient: ServiceOrderRecipient) -> list[dict[str, Any]]:
    result = _recipient_result(recipient)
    wa = result.get("wa_conversation") if isinstance(result.get("wa_conversation"), dict) else {}
    answers = wa.get("answers") or []
    return [a for a in answers if isinstance(a, dict)]


def _had_low_rating(recipient: ServiceOrderRecipient) -> bool:
    from app.services.survey_results_service import _is_negative_answer_value, _is_unhappy_respondent

    if _is_unhappy_respondent(recipient):
        return True
    for item in _wa_answers(recipient):
        for key in ("answer", "answer_text", "normalized_value"):
            val = str(item.get(key) or "").strip()
            if _is_negative_answer_value(val) or val.lower() in LOW_ANSWERS:
                return True
    return False


def _has_written_reason(recipient: ServiceOrderRecipient) -> bool:
    for item in _wa_answers(recipient):
        role = str(item.get("step_role") or item.get("reply_type") or "").strip().lower()
        text = str(
            item.get("answer_text")
            or item.get("translated_text")
            or item.get("original_text")
            or item.get("answer")
            or ""
        ).strip()
        if not text or text.lower() == "skip":
            continue
        if "tell_us_more" in role or "followup" in role or "reason" in role or "final_feedback" in role:
            if len(text) >= 8:
                return True
        source = str(item.get("answer_source") or "").strip().lower()
        if source == "voice" and len(text) >= 8:
            return True
        if len(text) >= 12 and text.lower() not in LOW_ANSWERS and not text.isdigit():
            if role in {"open_text", "text", "final_feedback", "tell_us_more"} or item.get("reply_type") == "text":
                return True
    result = _recipient_result(recipient)
    final = str(result.get("final_additional_feedback") or "").strip()
    if len(final) >= 8:
        return True
    return False


def _callable_phone(phone: str | None) -> bool:
    value = str(phone or "").strip()
    return bool(value) and not value.startswith("web:")


def _is_arabic_order(order: ServiceOrder) -> bool:
    cfg = _order_config(order)
    for key in ("language", "locale", "survey_language", "template_language"):
        lang = str(cfg.get(key) or "").strip().lower()
        if lang.startswith("ar"):
            return True
    return False


def _build_recipient_session_summary(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    from app.services.survey_results_service import _is_negative_answer_value

    poor_topics: list[str] = []
    poor_answers: list[dict[str, str]] = []
    positive_topics: list[str] = []
    for item in _wa_answers(recipient):
        label = str(item.get("question") or item.get("topic") or item.get("template_name") or "Topic").strip()
        val = str(item.get("answer") or item.get("answer_text") or item.get("normalized_value") or "").strip()
        low = val.lower()
        if not val or low == "skip":
            continue
        if _is_negative_answer_value(val) or low in LOW_ANSWERS or low == "no":
            if label not in poor_topics:
                poor_topics.append(label)
            poor_answers.append({"question": label, "answer": val})
        elif "excellent" in low or "good" in low or low == "yes" or "spotless" in low or "smooth" in low:
            if label not in positive_topics:
                positive_topics.append(label)

    why_parts = [f"{a['question']}: {a['answer']}" for a in poor_answers[:8]]
    result = _recipient_result(recipient)
    final = str(result.get("final_additional_feedback") or "").strip() or None
    from app.services.ai_followup_report_service import extract_wa_written_feedback

    written_feedback = extract_wa_written_feedback(_wa_answers(recipient), final_additional=final)
    why_unhappy = "; ".join(why_parts) if why_parts else "Low rating with no written reason given in the survey."
    return {
        "poor_topics": poor_topics,
        "poor_answers": poor_answers,
        "positive_topics": positive_topics,
        "no_topics": [],
        "written_feedback": written_feedback,
        "why_unhappy": why_unhappy,
    }


def _build_org_context_for_order(db: Session, *, org, order: ServiceOrder) -> str:
    parts: list[str] = []
    org_name = str(getattr(org, "name", None) or "").strip()
    if org_name:
        parts.append(f"Organisation: {org_name}")
    notes = str(getattr(org, "profile_notes", None) or "").strip()
    if notes:
        parts.append(f"Business notes: {notes[:1200]}")
    title = str(order.title or "").strip()
    if title:
        parts.append(f"Survey: {title}")
    cfg = _order_config(order)
    industry = str(cfg.get("industry_name") or cfg.get("industry") or "").strip()
    if industry:
        parts.append(f"Industry: {industry}")
    return "\n".join(parts)


def schedule_wa_if_eligible(db: Session, *, order: ServiceOrder, recipient: ServiceOrderRecipient) -> bool:
    """Enqueue AI follow-up when WA Survey order has AI follow-up enabled and recipient is eligible."""
    if str(order.service_code or "") != "survey":
        return False
    cfg = load_ai_follow_up_from_order(order)
    if not cfg.get("enabled"):
        return False
    if _is_arabic_order(order):
        return False
    if not _callable_phone(recipient.phone):
        return False
    if not _had_low_rating(recipient):
        return False
    if _has_written_reason(recipient):
        return False

    from app.services.uk_compliance_opt_out import should_block_outbound_phone

    if should_block_outbound_phone(db, org_id=order.org_id, phone_e164=str(recipient.phone or "")):
        return False

    delay_hours = resolve_followup_delay_hours(cfg)
    scheduled_at = datetime.now(timezone.utc) + timedelta(hours=delay_hours)

    existing = db.execute(
        select(SurveyAiFollowUpJob).where(SurveyAiFollowUpJob.recipient_id == recipient.id)
    ).scalar_one_or_none()
    if existing is not None:
        return False

    job = SurveyAiFollowUpJob(
        id=str(uuid.uuid4()),
        org_id=order.org_id,
        order_id=order.id,
        recipient_id=recipient.id,
        visitor_phone=str(recipient.phone or "").strip(),
        business_context=str(cfg.get("business_context") or cfg.get("businessContext") or "").strip(),
        promo_enabled=bool(cfg.get("promo_enabled") or cfg.get("promoEnabled")),
        promo_code=str(cfg.get("promo_code") or cfg.get("promoCode") or "").strip() or None,
        promo_description=str(cfg.get("promo_description") or cfg.get("promoDescription") or "").strip() or None,
        scheduled_at=scheduled_at.replace(tzinfo=None),
        status="scheduled",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    summary = _build_recipient_session_summary(recipient)
    _set_job_outcome(
        job,
        {
            "session_summary": summary,
            "why_unhappy": summary.get("why_unhappy"),
            "scheduled_reason": "low_rating_no_written_reason",
        },
    )
    db.add(job)
    db.commit()
    logger.info(
        "survey_ai_followup_scheduled order_id=%s recipient_id=%s scheduled_at=%s delay_hours=%s",
        order.id,
        recipient.id,
        scheduled_at.isoformat(),
        delay_hours,
    )
    return True


def _pre_dial_guards_wa(db: Session, job: SurveyAiFollowUpJob, org) -> None:
    from app.core.config import get_settings
    from app.services.uk_compliance_opt_out import should_block_outbound_phone

    settings = get_settings()
    if not bool(getattr(settings, "ai_followup_relax_calling_hours", False)):
        allowed, reason = org_calling_allowed(db, job.org_id, now=now_uk())
        if not allowed:
            raise FollowUpDefer(reason or "Outside calling hours", until=_next_calling_window_utc(db, job.org_id))

    skip = should_block_outbound_phone(db, org_id=job.org_id, phone_e164=str(job.visitor_phone or ""))
    if skip:
        raise FollowUpSkip(skip, status="opted_out")

    billing_ok, billing_reason, billing_mode = _pre_dial_billing_allowed(db, org)
    if not billing_ok:
        if billing_mode == "wallet":
            raise FollowUpSkip(billing_reason, status="blocked_low_balance")
        raise FollowUpSkip(billing_reason or "Billing blocked", status="failed")


def _dispatch_wa_job(db: Session, job: SurveyAiFollowUpJob) -> str | None:
    from app.models.organisation import Organisation
    from app.services.telnyx_api_key import normalize_telnyx_e164, telnyx_outbound_caller_id
    from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService
    from app.services.telnyx_voice_service import TelnyxVoiceAdapter, _telnyx_config

    org = db.get(Organisation, job.org_id)
    if org is None:
        raise RuntimeError("Organisation not found")
    order = db.get(ServiceOrder, job.order_id)
    if order is None:
        raise RuntimeError("Survey order not found")
    recipient = db.get(ServiceOrderRecipient, job.recipient_id)
    if recipient is None:
        raise RuntimeError("Recipient not found")

    org_name = str(org.name or "the business").strip() or "the business"
    _pre_dial_guards_wa(db, job, org)

    assistant_id, agent = _resolve_followback_assistant(db, job.org_id)
    if not assistant_id:
        raise RuntimeError("No Telnyx follow-back assistant configured")

    telnyx_config = _telnyx_config(db)
    from_number = telnyx_outbound_caller_id(telnyx_config)
    if not from_number:
        raise RuntimeError("Telnyx outbound caller ID is not configured")

    phone_check = TelnyxPhoneAllowlistService.validate_phone_db(db, str(job.visitor_phone or ""))
    if not phone_check.get("allowed"):
        raise RuntimeError(phone_check.get("reason") or "Phone number not allowed")

    session_summary = _build_recipient_session_summary(recipient)
    org_context = _build_org_context_for_order(db, org=org, order=order)
    greeting, instructions = _build_followup_instructions(
        job,
        org_name=org_name,
        org_context=org_context,
        session_summary=session_summary,
    )
    to_number = normalize_telnyx_e164(str(job.visitor_phone or ""))

    result = TelnyxVoiceAdapter.start_outbound_call(
        to_number=to_number,
        from_number=from_number,
        config=telnyx_config,
        enable_media_stream=False,
        client_state={
            "survey_ai_followup": True,
            "survey_ai_followup_job_id": job.id,
            "org_id": job.org_id,
            "order_id": job.order_id,
            "recipient_id": job.recipient_id,
            "agent_id": agent.id if agent else None,
            "telnyx_assistant_id": assistant_id,
            "survey_greeting": greeting,
            "survey_instructions": instructions[:4000],
            "promo_enabled": bool(job.promo_enabled),
            "promo_code": job.promo_code,
            "promo_description": job.promo_description,
        },
    )
    if not result.ok or not result.external_id:
        raise RuntimeError(result.detail or result.status or "dial_failed")

    _set_job_outcome(
        job,
        {
            "session_summary": session_summary,
            "dispatched_at": datetime.utcnow().isoformat(),
            "source": "wa_survey",
        },
    )
    logger.info(
        "survey_ai_followup_dialled job_id=%s call_id=%s order_id=%s",
        job.id,
        result.external_id,
        job.order_id,
    )
    return str(result.external_id)


def process_due_wa_jobs(db: Session, *, limit: int = 20) -> int:
    now = datetime.utcnow()
    rows = (
        db.execute(
            select(SurveyAiFollowUpJob)
            .where(SurveyAiFollowUpJob.status == "scheduled")
            .where(SurveyAiFollowUpJob.scheduled_at <= now)
            .order_by(SurveyAiFollowUpJob.scheduled_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    dispatched = 0
    for job in rows:
        try:
            call_id = _dispatch_wa_job(db, job)
            job.status = "dispatched"
            job.call_id = call_id
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            dispatched += 1
        except FollowUpDefer as exc:
            job.scheduled_at = exc.until or _next_calling_window_utc(db, job.org_id)
            _set_job_outcome(job, {"defer_reason": exc.reason, "deferred_at": datetime.utcnow().isoformat()})
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            logger.info("survey_ai_followup_deferred job_id=%s reason=%s until=%s", job.id, exc.reason, job.scheduled_at)
        except FollowUpSkip as exc:
            job.status = exc.status
            _set_job_outcome(job, {"skip_reason": exc.reason})
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            logger.info("survey_ai_followup_skipped job_id=%s status=%s reason=%s", job.id, exc.status, exc.reason)
        except Exception:
            logger.exception("survey_ai_followup_dispatch_failed job_id=%s", job.id)
            job.status = "failed"
            _set_job_outcome(job, {"error": "dispatch_failed"})
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
    return dispatched


def jobs_for_order(db: Session, order_id: str) -> list[SurveyAiFollowUpJob]:
    return list(
        db.execute(
            select(SurveyAiFollowUpJob)
            .where(SurveyAiFollowUpJob.order_id == order_id)
            .order_by(SurveyAiFollowUpJob.created_at.desc())
        )
        .scalars()
        .all()
    )


def jobs_by_recipient_ids(db: Session, recipient_ids: list[str]) -> dict[str, SurveyAiFollowUpJob]:
    if not recipient_ids:
        return {}
    rows = (
        db.execute(select(SurveyAiFollowUpJob).where(SurveyAiFollowUpJob.recipient_id.in_(recipient_ids)))
        .scalars()
        .all()
    )
    return {str(j.recipient_id): j for j in rows}


def job_to_report_dict(job: SurveyAiFollowUpJob) -> dict[str, Any]:
    outcome = _job_outcome(job)
    promo_email = outcome.get("promo_email") if isinstance(outcome.get("promo_email"), dict) else None
    report = {
        "id": job.id,
        "recipient_id": job.recipient_id,
        "visitor_phone": job.visitor_phone,
        "status": job.status,
        "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
        "call_id": job.call_id,
        "business_context": job.business_context,
        "promo_enabled": bool(job.promo_enabled),
        "promo_code": job.promo_code,
        "promo_email": promo_email,
        "outcome": outcome,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }
    try:
        from sqlalchemy.orm import object_session

        from app.services.ai_followup_call_media_service import attach_call_media_to_report

        db = object_session(job)
        if db is not None:
            report = attach_call_media_to_report(db, report, job)
    except Exception:
        logger.exception("survey_ai_followup_report_media_failed job_id=%s", job.id)
    return report


def handle_survey_ai_followup_telnyx_event(db: Session, payload: dict[str, Any]) -> bool:
    """Return True if payload was handled as a WA Survey AI follow-up call."""
    from app.models.call_log import CallLog
    from app.models.organisation import Organisation
    from app.services.survey_call_dispatch_service import _is_voicemail_telnyx_event
    from app.services.survey_voice_agent_service import detect_opt_out_text
    from app.services.telnyx_voice_service import TelnyxVoiceAdapter, _decode_client_state, _telnyx_config

    data = payload.get("data") or payload
    event_type = str(data.get("event_type") or payload.get("event_type") or "").lower()
    record = data.get("payload") if isinstance(data.get("payload"), dict) else data
    call_id = str(record.get("call_control_id") or record.get("call_leg_id") or record.get("id") or "").strip()
    if not call_id:
        return False

    client_state_raw = record.get("client_state")
    parsed = _decode_client_state(client_state_raw) if isinstance(client_state_raw, str) else None
    if not parsed or not parsed.get("survey_ai_followup"):
        return False

    job_id = str(parsed.get("survey_ai_followup_job_id") or "").strip()
    if not job_id:
        return False

    job = db.get(SurveyAiFollowUpJob, job_id)
    if job is None:
        return True

    if str(job.status or "").lower() in FOLLOWUP_TERMINAL:
        return True

    outcome = _job_outcome(job)
    telnyx_config = _telnyx_config(db)
    assistant_id = str(parsed.get("telnyx_assistant_id") or "").strip()

    if _is_voicemail_telnyx_event(event_type, record):
        job.status = "voicemail"
        outcome.update({"call_control_id": call_id, "voicemail_at": datetime.utcnow().isoformat()})
        job.outcome_json = json.dumps(outcome, ensure_ascii=False)
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        return True

    if "answered" in event_type:
        greeting = str(parsed.get("survey_greeting") or "").strip()
        instructions = str(parsed.get("survey_instructions") or "").strip()
        if not assistant_id:
            job.status = "failed"
            outcome.update({"error": "followback_assistant_not_configured", "call_control_id": call_id})
            job.outcome_json = json.dumps(outcome, ensure_ascii=False)
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            return True

        result = TelnyxVoiceAdapter.start_ai_assistant(
            call_control_id=call_id,
            assistant_id=assistant_id,
            config=telnyx_config,
            instructions=instructions,
            greeting=greeting,
            prepared=False,
        )
        if not result.ok:
            job.status = "failed"
            outcome.update({"error": result.detail or result.status, "call_control_id": call_id})
        else:
            outcome.update(
                {
                    "call_control_id": call_id,
                    "assistant_started_at": datetime.utcnow().isoformat(),
                    "assistant_status": result.status,
                }
            )
        job.outcome_json = json.dumps(outcome, ensure_ascii=False)
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        return True

    if "hangup" in event_type or "ended" in event_type:
        hangup_cause = str(record.get("hangup_cause") or record.get("sip_hangup_cause") or "").lower()
        no_answer_causes = {"no_answer", "originator_cancel", "timeout", "unallocated_number"}
        busy_causes = {"user_busy", "busy"}

        duration_seconds = None
        for key in ("duration_secs", "duration_seconds", "duration", "call_duration_secs"):
            raw = record.get(key)
            if raw is not None:
                try:
                    duration_seconds = int(raw)
                    break
                except (TypeError, ValueError):
                    pass

        transcript = None
        log = db.execute(select(CallLog).where(CallLog.external_call_id == call_id)).scalar_one_or_none()
        if log and log.transcript_text:
            transcript = log.transcript_text

        if transcript and detect_opt_out_text(transcript):
            job.status = "opted_out"
            outcome.update({"opt_out": True, "transcript_excerpt": transcript[:500]})
        elif any(c in hangup_cause for c in busy_causes) or "busy" in hangup_cause:
            job.status = "busy"
        elif any(c in hangup_cause for c in no_answer_causes) or "no answer" in hangup_cause:
            job.status = "no_answer"
        elif outcome.get("assistant_started_at"):
            job.status = "completed"
        elif str(job.status or "").lower() == "dispatched":
            job.status = "no_answer"
        else:
            job.status = "failed"

        answered = bool(outcome.get("assistant_started_at"))
        org = db.get(Organisation, job.org_id)
        if org is not None:
            try:
                billing = _settle_followup_call_billing(
                    db,
                    job=job,
                    org=org,
                    duration_seconds=duration_seconds,
                    call_log_id=None,
                    answered=answered,
                )
                outcome["billing"] = billing
            except Exception:
                logger.exception("survey_ai_followup_billing_failed job_id=%s", job.id)

        if str(job.status or "").lower() == "completed" and job.promo_enabled and job.promo_code:
            try:
                from app.services.survey_codes_email_service import send_followup_promo_email

                recipient = db.get(ServiceOrderRecipient, job.recipient_id)
                to_email = str(getattr(recipient, "email", None) or "").strip() if recipient else ""
                org_name = str(getattr(org, "name", None) or "the business") if org else "the business"
                customer_name = ""
                if recipient is not None:
                    customer_name = str(getattr(recipient, "name", None) or "").strip()
                outcome["promo_email"] = send_followup_promo_email(
                    db,
                    to_email=to_email,
                    org_name=org_name,
                    promo_code=str(job.promo_code),
                    promo_description=job.promo_description,
                    customer_name=customer_name or None,
                )
            except Exception:
                logger.exception("survey_ai_followup_promo_email_failed job_id=%s", job.id)
                outcome["promo_email"] = {"ok": False, "reason": "send_exception"}

        outcome.update(
            {
                "call_control_id": call_id,
                "hangup_at": datetime.utcnow().isoformat(),
                "duration_seconds": duration_seconds,
                "hangup_cause": hangup_cause,
                "transcript": transcript,
                "transcript_excerpt": (transcript[:800] if transcript else outcome.get("transcript_excerpt")),
            }
        )
        job.outcome_json = json.dumps(outcome, ensure_ascii=False)
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        if str(job.status or "").lower() in {"completed", "opted_out"}:
            try:
                from app.services.ai_followup_call_media_service import ensure_ai_followup_call_media

                ensure_ai_followup_call_media(db, job)
            except Exception:
                logger.exception("survey_ai_followup_media_hydrate_failed job_id=%s", job.id)
        return True

    if "speak" in event_type or "conversation" in event_type:
        text = str(record.get("text") or record.get("transcript") or "").strip()
        if text and detect_opt_out_text(text):
            job.status = "opted_out"
            outcome.update({"opt_out_text": text[:500]})
            job.outcome_json = json.dumps(outcome, ensure_ascii=False)
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
        return True

    return True
