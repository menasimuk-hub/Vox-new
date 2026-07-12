"""Schedule and dispatch AI voice follow-up for unhappy Customer Feedback respondents."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackLocation, FeedbackResponse, FeedbackSession
from app.utils.ofcom import now_uk, org_calling_allowed

logger = logging.getLogger(__name__)

LOW_ANSWERS = frozenset({"poor", "bad", "no", "maybe", "slow", "avg"})
FOLLOWUP_TERMINAL = frozenset(
    {
        "completed",
        "no_answer",
        "failed",
        "busy",
        "cancelled",
        "opted_out",
        "blocked_low_balance",
        "voicemail",
    }
)
PAYG_MIN_WALLET_MINOR = 500
RECOVERY_RULES = (
    "Recovery call rules:\n"
    "- Open softly: refer to 'recent feedback' — never say 'you gave us a low rating'.\n"
    "- Ask one open question about the lowest-scoring topic only; do not re-run the survey.\n"
    "- Listen more than you talk; summarise what you heard and thank them.\n"
    "- Never argue, defend, or blame the customer or staff by name.\n"
    "- If they are busy or upset, apologise, offer a human callback, and end politely.\n"
    "- Keep the call under three minutes. English only."
)


class FollowUpDefer(Exception):
    """Defer dispatch — job stays scheduled for a later time."""

    def __init__(self, reason: str, *, until: datetime | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.until = until


class FollowUpSkip(Exception):
    """Skip dispatch permanently (opt-out, cancelled, etc.)."""

    def __init__(self, reason: str, *, status: str = "cancelled") -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


def parse_ai_follow_up_config(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            cfg = parsed.get("ai_follow_up")
            return cfg if isinstance(cfg, dict) else {}
    except json.JSONDecodeError:
        pass
    return {}


def load_ai_follow_up_from_location(location: FeedbackLocation) -> dict[str, Any]:
    raw = getattr(location, "survey_config_json", None)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            cfg = parsed.get("ai_follow_up")
            return cfg if isinstance(cfg, dict) else {}
    except json.JSONDecodeError:
        return {}
    return {}


def resolve_followup_delay_hours(cfg: dict[str, Any]) -> int:
    """Hours until dial. 0 = immediate (AI_FOLLOWUP_FORCE_IMMEDIATE or test config). Production stays 24/48."""
    from app.core.config import get_settings

    settings = get_settings()
    if bool(getattr(settings, "ai_followup_force_immediate", False)):
        return 0
    if bool(cfg.get("force_immediate") or cfg.get("forceImmediate") or cfg.get("allow_test_immediate")):
        return 0
    try:
        delay_hours = int(cfg.get("delay_hours") or cfg.get("delayHours") or 24)
    except (TypeError, ValueError):
        delay_hours = 24
    if delay_hours not in (0, 24, 48):
        delay_hours = 24
    return delay_hours


def _job_outcome(job) -> dict[str, Any]:
    raw = getattr(job, "outcome_json", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _set_job_outcome(job, patch: dict[str, Any]) -> None:
    data = _job_outcome(job)
    data.update(patch)
    job.outcome_json = json.dumps(data, ensure_ascii=False)


def _has_written_reason(db: Session, session_id: str) -> bool:
    rows = db.execute(select(FeedbackResponse).where(FeedbackResponse.session_id == session_id)).scalars().all()
    for row in rows:
        key = str(row.question_key or "")
        text = str(row.answer_text or row.original_text or "").strip()
        if not text or text.lower() == "skip":
            continue
        if key.endswith("__low_reason") or "tell_us_more" in key or row.answer_source == "voice":
            return True
        if len(text) >= 8:
            return True
    return False


def _had_low_rating(db: Session, session_id: str) -> bool:
    rows = db.execute(select(FeedbackResponse).where(FeedbackResponse.session_id == session_id)).scalars().all()
    for row in rows:
        val = str(row.answer_text or row.original_text or "").strip().lower()
        if val in LOW_ANSWERS or "poor" in val:
            return True
    return False


def _callable_phone(visitor_phone: str) -> bool:
    phone = str(visitor_phone or "").strip()
    return bool(phone) and not phone.startswith("web:")


def _is_arabic_session(session: FeedbackSession | None) -> bool:
    lang = str(getattr(session, "detected_language", None) or "").strip().lower()
    return lang.startswith("ar")


def _build_session_summary(db: Session, session_id: str) -> dict[str, Any]:
    from app.services.customer_feedback.feedback_results_aggregate import (
        classify_pge,
        classify_yn,
        load_template_index,
        template_meta,
    )

    rows = list(
        db.execute(select(FeedbackResponse).where(FeedbackResponse.session_id == session_id)).scalars().all()
    )
    if not rows:
        return {"poor_topics": [], "positive_topics": [], "no_topics": []}

    survey_type_ids = {str(r.survey_type_id) for r in rows if r.survey_type_id}
    templates = load_template_index(db, survey_type_ids=survey_type_ids)

    poor_topics: list[str] = []
    positive_topics: list[str] = []
    no_topics: list[str] = []

    for row in rows:
        answer = str(row.answer_text or row.original_text or "").strip()
        if not answer or answer.lower() == "skip":
            continue
        label, _role = template_meta(
            templates,
            survey_type_id=str(row.survey_type_id),
            question_key=str(row.question_key or ""),
        )
        pge = classify_pge(answer)
        yn = classify_yn(answer)
        if pge == "poor" or yn == "no":
            if label not in poor_topics:
                poor_topics.append(label)
        elif pge in {"excellent", "good"} or yn == "yes":
            if label not in positive_topics:
                positive_topics.append(label)
        elif yn == "no":
            if label not in no_topics:
                no_topics.append(label)

    return {"poor_topics": poor_topics, "positive_topics": positive_topics, "no_topics": no_topics}


def _build_org_context(db: Session, *, org, location: FeedbackLocation | None) -> str:
    parts: list[str] = []
    org_name = str(getattr(org, "name", None) or "").strip()
    if org_name:
        parts.append(f"Organisation: {org_name}")
    notes = str(getattr(org, "profile_notes", None) or "").strip()
    if notes:
        parts.append(f"Business notes: {notes[:1200]}")
    if location is not None:
        loc_name = str(getattr(location, "name", None) or "").strip()
        if loc_name:
            parts.append(f"Location: {loc_name}")
        try:
            from app.models.customer_feedback import FeedbackIndustry

            industry = db.get(FeedbackIndustry, location.industry_id)
            if industry and str(industry.name or "").strip():
                parts.append(f"Industry: {industry.name}")
        except Exception:
            pass
    return "\n".join(parts)


def _format_session_summary_for_prompt(summary: dict[str, Any]) -> str:
    poor = summary.get("poor_topics") or []
    positive = summary.get("positive_topics") or []
    no_topics = summary.get("no_topics") or []
    lines: list[str] = []
    if poor:
        lines.append("Rated poorly (focus here): " + "; ".join(poor))
    if positive:
        lines.append("Rated well (do not re-ask): " + "; ".join(positive))
    if no_topics:
        lines.append("Said no to: " + "; ".join(no_topics))
    if not lines:
        return "Customer gave low ratings but did not leave written detail."
    lines.append("Do not quote raw emoji or button labels to the customer.")
    return "\n".join(lines)


def _build_followup_instructions(
    job,
    *,
    org_name: str,
    org_context: str = "",
    session_summary: dict[str, Any] | None = None,
) -> tuple[str, str]:
    context = str(job.business_context or "").strip()
    summary_text = _format_session_summary_for_prompt(session_summary or {})
    promo = ""
    if job.promo_enabled and job.promo_code:
        promo = (
            f"\nIf the customer feels heard and is receptive, you may offer promo code {job.promo_code}"
            f" ({job.promo_description or 'recovery offer'}). Mention it once only."
        )
    instructions = (
        "You are making a service-recovery follow-up call after customer feedback.\n"
        f"Business: {org_name}\n"
        f"{org_context}\n"
        f"Venue context:\n{context or 'General service recovery call.'}\n\n"
        f"Survey summary (internal — do not read verbatim):\n{summary_text}\n\n"
        f"{RECOVERY_RULES}"
        f"{promo}"
    )
    greeting = (
        f"Hi, this is a quick follow-up from {org_name}. "
        "You recently shared some feedback with us and we wanted to understand how we can do better. "
        "This call is recorded for quality. Do you have a minute?"
    )
    return greeting, instructions


def _resolve_followback_assistant(db: Session, org_id: str) -> tuple[str, Any | None]:
    from app.core.config import get_settings
    from app.core.agent_services import SERVICE_FEEDBACK_FOLLOWUP, SERVICE_SURVEY
    from app.models.agent import AgentDefinition
    from app.services.agent_service_resolver import resolve_agent_for_org_service
    from app.services.telnyx_assistant_service import normalize_telnyx_assistant_id

    for service_key in (SERVICE_FEEDBACK_FOLLOWUP, SERVICE_SURVEY):
        try:
            agent = resolve_agent_for_org_service(db, org_id=org_id, service_key=service_key, require_active=True)
        except ValueError:
            agent = None
        if agent and str(agent.telnyx_assistant_id or "").strip():
            return normalize_telnyx_assistant_id(agent.telnyx_assistant_id), agent

    dedicated = db.execute(
        select(AgentDefinition)
        .where(
            AgentDefinition.is_active.is_(True),
            AgentDefinition.supports_survey.is_(True),
            AgentDefinition.slug == "feedback-followback-gb",
        )
        .limit(1)
    ).scalar_one_or_none()
    if dedicated and str(dedicated.telnyx_assistant_id or "").strip():
        return normalize_telnyx_assistant_id(dedicated.telnyx_assistant_id), dedicated

    default = db.execute(
        select(AgentDefinition)
        .where(
            AgentDefinition.is_active.is_(True),
            AgentDefinition.supports_survey.is_(True),
            AgentDefinition.is_default_survey.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    if default and str(default.telnyx_assistant_id or "").strip():
        return normalize_telnyx_assistant_id(default.telnyx_assistant_id), default

    configured = str(get_settings().survey_telnyx_assistant_id or "").strip()
    if configured:
        return normalize_telnyx_assistant_id(configured), dedicated or default
    return "", dedicated or default


def _next_calling_window_utc(db: Session, org_id: str) -> datetime:
    cursor = now_uk()
    for _ in range(96):
        allowed, _reason = org_calling_allowed(db, org_id, now=cursor)
        if allowed:
            return cursor.astimezone(timezone.utc).replace(tzinfo=None)
        cursor = cursor + timedelta(minutes=30)
    return (now_uk() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0).astimezone(
        timezone.utc
    ).replace(tzinfo=None)


def _pre_dial_billing_allowed(db: Session, org) -> tuple[bool, str, str]:
    from app.services.billing_access_service import BillingAccessService
    from app.services.launch_billing_service import LaunchBillingService
    from app.services.usage_wallet_service import UsageWalletService
    from app.services.wallet_service import WalletService

    block = BillingAccessService.launch_block_reason(db, org)
    sub = BillingAccessService.get_valid_core_subscription(db, org.id)
    has_subscription = sub is not None and block is None

    usage_row = UsageWalletService.get_current(db, org.id)
    calls_remaining = 0
    if usage_row is not None:
        calls_remaining = max(0, int(usage_row.calls_included or 0) - int(usage_row.calls_used or 0))

    if has_subscription:
        if not bool(getattr(org, "allow_overage", True)) and calls_remaining <= 0:
            return False, "No included AI minutes remaining and overage is disabled.", "subscription"
        return True, "", "subscription"

    if block:
        return False, block, "blocked"

    spendable = WalletService.spendable_minor(org, allow_promo=False)
    if spendable < PAYG_MIN_WALLET_MINOR:
        return (
            False,
            f"Wallet balance must be at least £5 for AI follow-back calls ({spendable}p available).",
            "wallet",
        )

    est = LaunchBillingService.estimate_phone_launch(
        db,
        org,
        recipient_count=1,
        duration_min=3,
        calls_remaining_min=0,
        has_subscription=False,
    )
    if not est.get("can_launch"):
        return False, str(est.get("block_reason") or "Insufficient wallet for estimated call cost."), "wallet"
    return True, "", "payg"


def _pre_dial_guards(db: Session, job, org) -> None:
    from app.services.uk_compliance_opt_out import should_block_outbound_phone

    allowed, reason = org_calling_allowed(db, job.org_id, now=now_uk())
    if not allowed:
        raise FollowUpDefer(reason or "Outside calling hours", until=_next_calling_window_utc(db, job.org_id))

    skip = should_block_outbound_phone(db, org_id=job.org_id, phone_e164=str(job.visitor_phone or ""))
    if skip:
        raise FollowUpSkip(skip, status="opted_out")

    session = db.get(FeedbackSession, job.session_id)
    if _is_arabic_session(session):
        raise FollowUpSkip("Arabic session — English-only follow-back skipped", status="cancelled")

    billing_ok, billing_reason, billing_mode = _pre_dial_billing_allowed(db, org)
    if not billing_ok:
        if billing_mode == "wallet":
            job.status = "blocked_low_balance"
            _set_job_outcome(job, {"billing_block": billing_reason, "billing_mode": billing_mode})
            raise FollowUpSkip(billing_reason, status="blocked_low_balance")
        raise FollowUpSkip(billing_reason or "Billing blocked", status="failed")


def _settle_followup_call_billing(
    db: Session,
    *,
    job,
    org,
    duration_seconds: int | None,
    call_log_id: int | None,
    answered: bool,
) -> dict[str, Any]:
    from app.services.billing_access_service import BillingAccessService
    from app.services.billing_call_minutes import billable_call_minutes
    from app.services.launch_billing_service import LaunchBillingService
    from app.services.usage_wallet_service import UsageWalletService
    from app.services.wallet_service import InsufficientWalletBalance, WalletService

    if not answered:
        return {"billing_skipped": True, "reason": "not_answered"}

    billable_mins = billable_call_minutes(int(duration_seconds or 0))
    block = BillingAccessService.launch_block_reason(db, org)
    sub = BillingAccessService.get_valid_core_subscription(db, org.id)
    has_subscription = sub is not None and block is None

    usage_row = UsageWalletService.get_current(db, org.id)
    calls_remaining = 0
    if usage_row is not None:
        calls_remaining = max(0, int(usage_row.calls_included or 0) - int(usage_row.calls_used or 0))

    est = LaunchBillingService.estimate_phone_launch(
        db,
        org,
        recipient_count=1,
        duration_min=max(1, billable_mins),
        calls_remaining_min=calls_remaining,
        has_subscription=has_subscription,
    )

    UsageWalletService.on_call_completed(
        db,
        org_id=job.org_id,
        call_log_id=call_log_id,
        duration_seconds=duration_seconds,
    )

    amount_due = int(est.get("amount_due_minor") or 0)
    method = str(est.get("payment_method") or "")
    billing: dict[str, Any] = {
        "channel": "ai_call_follow_back",
        "billable_minutes": billable_mins,
        "amount_due_minor": amount_due,
        "payment_method": method,
        "catalog_cost_minor": int(est.get("catalog_cost_minor") or 0),
    }

    if amount_due > 0 and method == "wallet":
        phone_tail = str(job.visitor_phone or "")[-4:]
        try:
            tx = WalletService.debit(
                db,
                org,
                amount_minor=amount_due,
                kind="ai_call_follow_back",
                description=f"AI follow-back · …{phone_tail} · {billable_mins}m"[:500],
                metadata={
                    "job_id": job.id,
                    "session_id": getattr(job, "session_id", None),
                    "recipient_id": getattr(job, "recipient_id", None),
                    "order_id": getattr(job, "order_id", None),
                    "call_log_id": call_log_id,
                    "billable_minutes": billable_mins,
                },
                restrict_promo_spend=True,
            )
            billing["wallet_transaction_id"] = tx.id
        except InsufficientWalletBalance as exc:
            billing["wallet_debit_failed"] = str(exc)
    elif amount_due > 0 and method == "direct_debit":
        billing["dd_deferred_minor"] = amount_due

    return billing


def schedule_if_eligible(db: Session, *, session: FeedbackSession, location: FeedbackLocation) -> bool:
    """Enqueue AI follow-up when config enabled and respondent is eligible."""
    cfg = load_ai_follow_up_from_location(location)
    if not cfg.get("enabled"):
        return False
    if not _callable_phone(session.visitor_phone):
        return False
    if _is_arabic_session(session):
        return False
    if not _had_low_rating(db, session.id):
        return False
    if _has_written_reason(db, session.id):
        return False

    from app.services.uk_compliance_opt_out import should_block_outbound_phone

    if should_block_outbound_phone(db, org_id=session.org_id, phone_e164=session.visitor_phone):
        return False

    delay_hours = resolve_followup_delay_hours(cfg)
    scheduled_at = datetime.now(timezone.utc) + timedelta(hours=delay_hours)

    from app.models.customer_feedback import FeedbackAiFollowUpJob

    existing = db.execute(
        select(FeedbackAiFollowUpJob).where(FeedbackAiFollowUpJob.session_id == session.id)
    ).scalar_one_or_none()
    if existing is not None:
        return False

    job = FeedbackAiFollowUpJob(
        id=str(uuid.uuid4()),
        org_id=session.org_id,
        location_id=session.location_id,
        session_id=session.id,
        visitor_phone=session.visitor_phone,
        business_context=str(cfg.get("business_context") or cfg.get("businessContext") or "").strip(),
        promo_enabled=bool(cfg.get("promo_enabled") or cfg.get("promoEnabled")),
        promo_code=str(cfg.get("promo_code") or cfg.get("promoCode") or "").strip(),
        promo_description=str(cfg.get("promo_description") or cfg.get("promoDescription") or "").strip(),
        scheduled_at=scheduled_at.replace(tzinfo=None),
        status="scheduled",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    logger.info(
        "feedback_ai_followup_scheduled session_id=%s scheduled_at=%s",
        session.id,
        scheduled_at.isoformat(),
    )
    return True


def process_due_jobs(db: Session, *, limit: int = 20) -> int:
    """Process due AI follow-up jobs. Returns count dispatched."""
    from app.models.customer_feedback import FeedbackAiFollowUpJob

    now = datetime.utcnow()
    rows = db.execute(
        select(FeedbackAiFollowUpJob)
        .where(FeedbackAiFollowUpJob.status == "scheduled")
        .where(FeedbackAiFollowUpJob.scheduled_at <= now)
        .order_by(FeedbackAiFollowUpJob.scheduled_at.asc())
        .limit(limit)
    ).scalars().all()

    dispatched = 0
    for job in rows:
        try:
            call_id = _dispatch_job(db, job)
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
            logger.info("feedback_ai_followup_deferred job_id=%s reason=%s until=%s", job.id, exc.reason, job.scheduled_at)
        except FollowUpSkip as exc:
            job.status = exc.status
            _set_job_outcome(job, {"skip_reason": exc.reason})
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            logger.info("feedback_ai_followup_skipped job_id=%s status=%s reason=%s", job.id, exc.status, exc.reason)
        except Exception:
            logger.exception("feedback_ai_followup_dispatch_failed job_id=%s", job.id)
            job.status = "failed"
            _set_job_outcome(job, {"error": "dispatch_failed"})
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
    return dispatched


def _dispatch_job(db: Session, job) -> str | None:
    """Dial the respondent via Telnyx using the follow-back voice assistant."""
    from app.models.organisation import Organisation
    from app.services.telnyx_api_key import normalize_telnyx_e164, telnyx_outbound_caller_id
    from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService
    from app.services.telnyx_voice_service import TelnyxVoiceAdapter, _telnyx_config

    org = db.get(Organisation, job.org_id)
    if org is None:
        raise RuntimeError("Organisation not found")
    location = db.get(FeedbackLocation, job.location_id)
    org_name = str(org.name or "the business").strip() or "the business"

    _pre_dial_guards(db, job, org)

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

    session_summary = _build_session_summary(db, job.session_id)
    org_context = _build_org_context(db, org=org, location=location)
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
            "feedback_ai_followup": True,
            "feedback_ai_followup_job_id": job.id,
            "org_id": job.org_id,
            "location_id": job.location_id,
            "session_id": job.session_id,
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
        },
    )

    logger.info(
        "feedback_ai_followup_dialled job_id=%s call_id=%s org_id=%s",
        job.id,
        result.external_id,
        job.org_id,
    )
    return str(result.external_id)


def job_to_report_dict(job) -> dict[str, Any]:
    outcome = _job_outcome(job)
    summary = outcome.get("session_summary") if isinstance(outcome.get("session_summary"), dict) else {}
    return {
        "id": job.id,
        "session_id": getattr(job, "session_id", None),
        "visitor_phone": job.visitor_phone,
        "status": job.status,
        "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
        "call_id": job.call_id,
        "business_context": job.business_context,
        "poor_topics": summary.get("poor_topics") or [],
        "positive_topics": summary.get("positive_topics") or [],
        "outcome": outcome,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def attach_ai_followup_to_feedback_respondents(db: Session, respondents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not respondents:
        return respondents
    from app.models.customer_feedback import FeedbackAiFollowUpJob

    ids = [str(r.get("id") or "") for r in respondents if r.get("id")]
    if not ids:
        return respondents
    rows = (
        db.execute(select(FeedbackAiFollowUpJob).where(FeedbackAiFollowUpJob.session_id.in_(ids)))
        .scalars()
        .all()
    )
    by_id = {str(j.session_id): j for j in rows}
    for row in respondents:
        job = by_id.get(str(row.get("id") or ""))
        if job is not None:
            report = job_to_report_dict(job)
            row["ai_follow_up"] = report
            row["ai_follow_up_status"] = report.get("status")
        else:
            row["ai_follow_up"] = None
            row["ai_follow_up_status"] = None
    return respondents


def handle_feedback_ai_followup_telnyx_event(db: Session, payload: dict[str, Any]) -> bool:
    """Return True if payload was handled as a Customer Feedback AI follow-up call."""
    from app.models.call_log import CallLog
    from app.models.customer_feedback import FeedbackAiFollowUpJob
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
    if not parsed or not parsed.get("feedback_ai_followup"):
        return False

    job_id = str(parsed.get("feedback_ai_followup_job_id") or "").strip()
    if not job_id:
        return False

    job = db.get(FeedbackAiFollowUpJob, job_id)
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
        for key in ("duration_secs", "duration_seconds", "duration"):
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
        billing: dict[str, Any] = {}
        if org is not None:
            billing = _settle_followup_call_billing(
                db,
                job=job,
                org=org,
                duration_seconds=duration_seconds,
                call_log_id=log.id if log else None,
                answered=answered,
            )

        outcome.update(
            {
                "call_control_id": call_id,
                "hangup_cause": hangup_cause or None,
                "duration_seconds": duration_seconds,
                "transcript": transcript,
                "billing": billing,
                "completed_at": datetime.utcnow().isoformat(),
            }
        )
        job.outcome_json = json.dumps(outcome, ensure_ascii=False)
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        return True

    return True
