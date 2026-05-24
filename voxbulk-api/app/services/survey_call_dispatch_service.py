from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_dispatch_service import _first_name, _personalize, _survey_intro_text
from app.services.telnyx_api_key import normalize_telnyx_e164, telnyx_outbound_caller_id
from app.services.telnyx_assistant_service import normalize_telnyx_assistant_id
from app.services.telnyx_voice_service import TelnyxVoiceAdapter, _decode_client_state, _telnyx_config
from app.utils.ofcom import is_within_calling_window, now_uk

logger = get_logger(__name__)

LOG_PREFIX = "[survey-call]"

VOICE_PENDING = {"pending", ""}
VOICE_TERMINAL = {"completed", "no_answer", "failed", "busy", "skipped", "cancelled"}
VOICE_ACTIVE = {"calling"}


def _log(event: str, **detail: Any) -> None:
    logger.info("%s %s", LOG_PREFIX, event, extra=detail)


def get_survey_telnyx_assistant_id(db: Session) -> str:
    from app.core.config import get_settings
    from app.services.lead_sales_service import get_lead_sales_settings

    configured = str(get_settings().survey_telnyx_assistant_id or "").strip()
    if configured:
        return normalize_telnyx_assistant_id(configured)
    settings = get_lead_sales_settings(db)
    fallback = str(settings.telnyx_assistant_id or "").strip()
    if fallback:
        return normalize_telnyx_assistant_id(fallback)
    return ""


def is_ai_call_survey_order(order: ServiceOrder) -> bool:
    if order.service_code != "survey":
        return False
    try:
        config = json.loads(order.config_json or "{}")
        return PlatformCatalogService.resolve_survey_channel(config) == "ai_call"
    except Exception:
        return False


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _set_recipient_result(db: Session, recipient: ServiceOrderRecipient, payload: dict[str, Any]) -> None:
    merged = _recipient_result(recipient)
    merged.update(payload)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)


def build_survey_call_instructions(config: dict[str, Any], *, recipient_name: str) -> str:
    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "the organisation").strip()
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
    first = _first_name(recipient_name)
    system = str(config.get("system_prompt") or "").strip()
    script = str(config.get("approved_script") or "").strip()
    goal = str(config.get("goal") or "").strip()

    parts: list[str] = []
    if system:
        parts.append(system)
    else:
        parts.append(
            "You are conducting a short outbound phone survey on behalf of the client's organisation. "
            "Be warm, concise, and professional. Ask the survey questions clearly and listen to answers."
        )
    if goal:
        parts.append(f"Survey goal: {goal}")
    parts.append(f"Organisation name: {org_name}")
    parts.append(f"Survey organiser (name used on the call): {organiser}")
    parts.append(f"Contact first name: {first}")
    if script:
        parts.append(
            "Approved survey script (follow this structure):\n"
            + _personalize(script, first_name=first, org_name=org_name, organiser=organiser)
        )
    return "\n\n".join(parts)


def build_survey_call_greeting(config: dict[str, Any], *, recipient_name: str) -> str:
    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "your provider").strip()
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
    first = _first_name(recipient_name)
    intro = _survey_intro_text(config)
    greeting = _personalize(intro, first_name=first, org_name=org_name, organiser=organiser)
    if greeting:
        return greeting
    return f"Hi {first}, this is a quick survey call from {org_name}."


def _order_window_ok(order: ServiceOrder, *, now: datetime | None = None) -> tuple[bool, str | None]:
    now = now or datetime.utcnow()
    if order.scheduled_end_at and now >= order.scheduled_end_at:
        return False, "Survey calling window has ended"
    if not is_within_calling_window(now_uk()):
        return False, "Outside UK calling hours"
    return True, None


def _refresh_order_report(db: Session, order: ServiceOrder) -> None:
    from app.services.survey_analysis_service import refresh_order_survey_report

    refresh_order_survey_report(db, order)


def _any_recipient_calling(recipients: list[ServiceOrderRecipient]) -> bool:
    return any(str(r.status or "").lower() in VOICE_ACTIVE for r in recipients)


def _all_recipients_terminal(recipients: list[ServiceOrderRecipient]) -> bool:
    if not recipients:
        return True
    return all(str(r.status or "pending").lower() in VOICE_TERMINAL for r in recipients)


def _finalize_order_if_done(db: Session, order: ServiceOrder) -> ServiceOrder:
    recipients = ServiceOrderService.get_recipients(db, order.id)
    _refresh_order_report(db, order)
    if _all_recipients_terminal(recipients):
        order.status = "completed"
        order.completed_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        _log("order_completed", order_id=order.id)
    return order


def _complete_order_window_expired(db: Session, order: ServiceOrder, *, reason: str) -> ServiceOrder:
    recipients = ServiceOrderService.get_recipients(db, order.id)
    for recipient in recipients:
        if str(recipient.status or "pending").lower() in VOICE_PENDING | VOICE_ACTIVE:
            recipient.status = "cancelled"
            _set_recipient_result(
                db,
                recipient,
                {"error": reason, "cancelled_at": datetime.utcnow().isoformat()},
            )
    from app.services.survey_analysis_service import build_order_survey_report

    recipients = ServiceOrderService.get_recipients(db, order.id)
    report = build_order_survey_report(order, recipients)
    report["note"] = reason
    order.report_json = json.dumps(report, ensure_ascii=False)
    order.status = "completed"
    order.completed_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    _log("order_window_ended", order_id=order.id, reason=reason)
    return order


class SurveyCallDispatchService:
    @staticmethod
    def process_due_orders(db: Session, *, limit: int = 5) -> int:
        now = datetime.utcnow()
        started = 0
        due = list(
            db.execute(
                select(ServiceOrder)
                .where(
                    ServiceOrder.service_code == "survey",
                    ServiceOrder.payment_status == "approved",
                    ServiceOrder.status.in_(["scheduled", "paid"]),
                    ServiceOrder.scheduled_start_at.is_not(None),
                    ServiceOrder.scheduled_start_at <= now,
                )
                .order_by(ServiceOrder.scheduled_start_at.asc())
                .limit(limit)
            ).scalars()
        )
        for order in due:
            if not is_ai_call_survey_order(order):
                continue
            try:
                if SurveyCallDispatchService.start_campaign(db, order):
                    started += 1
            except Exception as exc:
                _log("start_failed", order_id=order.id, error=str(exc))
                logger.exception("survey_call_start_failed")

        running = list(
            db.execute(
                select(ServiceOrder)
                .where(ServiceOrder.service_code == "survey", ServiceOrder.status == "running")
                .order_by(ServiceOrder.updated_at.asc())
                .limit(limit)
            ).scalars()
        )
        for order in running:
            if not is_ai_call_survey_order(order):
                continue
            try:
                SurveyCallDispatchService.tick_running_order(db, order)
            except Exception as exc:
                _log("tick_failed", order_id=order.id, error=str(exc))
                logger.exception("survey_call_tick_failed")
        return started

    @staticmethod
    def start_campaign(db: Session, order: ServiceOrder) -> bool:
        if order.status not in {"scheduled", "paid"}:
            return False
        if not is_ai_call_survey_order(order):
            return False
        if order.payment_status != "approved":
            return False

        assistant_id = get_survey_telnyx_assistant_id(db)
        if not assistant_id:
            _log("assistant_missing", order_id=order.id)
            return False

        ok, reason = _order_window_ok(order)
        if not ok:
            _log("window_blocked_at_start", order_id=order.id, reason=reason)
            return False

        config = _order_config(order)
        if not config.get("script_approved") and not str(config.get("approved_script") or "").strip():
            _log("script_not_approved", order_id=order.id)
            return False

        now = datetime.utcnow()
        order.status = "running"
        order.started_at = order.started_at or now
        order.updated_at = now
        db.add(order)
        db.commit()
        db.refresh(order)
        _log("campaign_started", order_id=order.id, org_id=order.org_id)
        _refresh_order_report(db, order)
        return SurveyCallDispatchService.dial_next_recipient(db, order) is not None

    @staticmethod
    def tick_running_order(db: Session, order: ServiceOrder) -> None:
        if order.status != "running":
            return
        ok, reason = _order_window_ok(order)
        if not ok:
            _complete_order_window_expired(db, order, reason=reason or "window_ended")
            return

        recipients = ServiceOrderService.get_recipients(db, order.id)
        if _all_recipients_terminal(recipients):
            _finalize_order_if_done(db, order)
            return
        if _any_recipient_calling(recipients):
            return
        SurveyCallDispatchService.dial_next_recipient(db, order)

    @staticmethod
    def dial_next_recipient(db: Session, order: ServiceOrder) -> ServiceOrderRecipient | None:
        if order.status != "running":
            return None

        assistant_id = get_survey_telnyx_assistant_id(db)
        if not assistant_id:
            return None

        ok, reason = _order_window_ok(order)
        if not ok:
            _complete_order_window_expired(db, order, reason=reason or "window_ended")
            return None

        recipients = ServiceOrderService.get_recipients(db, order.id)
        if _any_recipient_calling(recipients):
            return None

        next_recipient = next(
            (r for r in recipients if str(r.status or "pending").lower() in VOICE_PENDING),
            None,
        )
        if next_recipient is None:
            _finalize_order_if_done(db, order)
            return None

        config = _order_config(order)
        telnyx_config = _telnyx_config(db)
        from_number = telnyx_outbound_caller_id(telnyx_config)
        if not from_number:
            _log("caller_id_missing", order_id=order.id)
            return None

        instructions = build_survey_call_instructions(config, recipient_name=next_recipient.name)
        greeting = build_survey_call_greeting(config, recipient_name=next_recipient.name)
        to_number = normalize_telnyx_e164(str(next_recipient.phone or ""))

        result = TelnyxVoiceAdapter.start_outbound_call(
            to_number=to_number,
            from_number=from_number,
            config=telnyx_config,
            client_state={
                "survey_call": True,
                "service_order_id": order.id,
                "recipient_id": next_recipient.id,
                "org_id": order.org_id,
                "telnyx_assistant_id": assistant_id,
                "survey_greeting": greeting,
                "survey_instructions": instructions[:4000],
            },
        )

        now = datetime.utcnow()
        if not result.ok or not result.external_id:
            next_recipient.status = "failed"
            _set_recipient_result(
                db,
                next_recipient,
                {
                    "channel": "ai_call",
                    "error": result.detail or result.status or "dial_failed",
                    "failed_at": now.isoformat(),
                },
            )
            _refresh_order_report(db, order)
            _log("dial_failed", order_id=order.id, recipient_id=next_recipient.id, detail=result.detail)
            return next_recipient

        next_recipient.status = "calling"
        _set_recipient_result(
            db,
            next_recipient,
            {
                "channel": "ai_call",
                "call_control_id": result.external_id,
                "provider_status": result.status,
                "started_at": now.isoformat(),
            },
        )
        _refresh_order_report(db, order)
        _log(
            "dial_started",
            order_id=order.id,
            recipient_id=next_recipient.id,
            call_control_id=result.external_id,
        )
        return next_recipient

    @staticmethod
    def finalize_recipient_after_call(
        db: Session,
        *,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        status: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        recipient.status = status
        payload = {
            "channel": "ai_call",
            "final_status": status,
            "ended_at": datetime.utcnow().isoformat(),
        }
        if extra:
            payload.update(extra)
        merged = _recipient_result(recipient)
        merged.update(payload)
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        db.refresh(recipient)
        _refresh_order_report(db, order)

        recipients = ServiceOrderService.get_recipients(db, order.id)
        if order.status == "running" and not _any_recipient_calling(recipients):
            ok, reason = _order_window_ok(order)
            if not ok:
                _complete_order_window_expired(db, order, reason=reason or "window_ended")
            elif _all_recipients_terminal(recipients):
                _finalize_order_if_done(db, order)
            else:
                SurveyCallDispatchService.dial_next_recipient(db, order)


def handle_survey_telnyx_event(db: Session, payload: dict[str, Any]) -> bool:
    """Return True if payload was handled as a survey voice call."""
    data = payload.get("data") or payload
    event_type = str(data.get("event_type") or payload.get("event_type") or "").lower()
    record = data.get("payload") if isinstance(data.get("payload"), dict) else data
    call_id = str(record.get("call_control_id") or record.get("call_leg_id") or record.get("id") or "").strip()
    if not call_id:
        return False

    client_state_raw = record.get("client_state")
    parsed = _decode_client_state(client_state_raw) if isinstance(client_state_raw, str) else None
    if not parsed or not parsed.get("survey_call"):
        return False

    order_id = str(parsed.get("service_order_id") or "").strip()
    recipient_id = str(parsed.get("recipient_id") or "").strip()
    if not order_id or not recipient_id:
        return False

    order = ServiceOrderService.get_order(db, order_id)
    recipient = db.get(ServiceOrderRecipient, recipient_id)
    if order is None or recipient is None or recipient.order_id != order.id:
        return False

    if str(recipient.status or "").lower() in VOICE_TERMINAL:
        return True

    assistant_id = str(parsed.get("telnyx_assistant_id") or get_survey_telnyx_assistant_id(db) or "").strip()
    config = _telnyx_config(db)

    if "answered" in event_type:
        config_order = _order_config(order)
        instructions = str(parsed.get("survey_instructions") or "").strip() or build_survey_call_instructions(
            config_order,
            recipient_name=recipient.name,
        )
        greeting = str(parsed.get("survey_greeting") or "").strip() or build_survey_call_greeting(
            config_order,
            recipient_name=recipient.name,
        )
        if not assistant_id:
            SurveyCallDispatchService.finalize_recipient_after_call(
                db,
                order=order,
                recipient=recipient,
                status="failed",
                extra={"error": "survey_assistant_not_configured", "call_control_id": call_id},
            )
            return True

        result = TelnyxVoiceAdapter.start_ai_assistant(
            call_control_id=call_id,
            assistant_id=assistant_id,
            config=config,
            instructions=instructions,
            greeting=greeting,
            prepared=False,
        )
        if not result.ok:
            SurveyCallDispatchService.finalize_recipient_after_call(
                db,
                order=order,
                recipient=recipient,
                status="failed",
                extra={
                    "error": result.detail or result.status,
                    "call_control_id": call_id,
                },
            )
        else:
            _set_recipient_result(
                db,
                recipient,
                {
                    "call_control_id": call_id,
                    "assistant_started_at": datetime.utcnow().isoformat(),
                    "assistant_status": result.status,
                },
            )
            _log("assistant_started", order_id=order.id, recipient_id=recipient.id, call_control_id=call_id)
        return True

    if "hangup" in event_type or "ended" in event_type:
        hangup_cause = str(record.get("hangup_cause") or record.get("sip_hangup_cause") or "").lower()
        no_answer_causes = {"no_answer", "originator_cancel", "timeout", "unallocated_number"}
        busy_causes = {"user_busy", "busy"}
        if any(c in hangup_cause for c in busy_causes) or "busy" in hangup_cause:
            terminal = "busy"
        elif any(c in hangup_cause for c in no_answer_causes) or "no answer" in hangup_cause:
            terminal = "no_answer"
        elif str(recipient.status or "").lower() == "calling":
            terminal = "completed"
        else:
            terminal = str(recipient.status or "failed").lower()
            if terminal not in VOICE_TERMINAL:
                terminal = "failed"

        transcript = None
        try:
            from app.models.call_log import CallLog

            log = db.execute(
                select(CallLog).where(CallLog.external_call_id == call_id)
            ).scalar_one_or_none()
            if log and log.transcript_text:
                transcript = log.transcript_text
        except Exception:
            pass

        duration_seconds = None
        for key in ("duration_secs", "duration_seconds", "duration"):
            raw = record.get(key)
            if raw is not None:
                try:
                    duration_seconds = int(raw)
                    break
                except (TypeError, ValueError):
                    pass

        hangup_extra = {
            "call_control_id": call_id,
            "hangup_cause": hangup_cause or None,
            "transcript": transcript,
            "duration_seconds": duration_seconds,
        }

        SurveyCallDispatchService.finalize_recipient_after_call(
            db,
            order=order,
            recipient=recipient,
            status=terminal,
            extra=hangup_extra,
        )

        try:
            from app.services.survey_analysis_service import (
                SurveyAnalysisService,
                schedule_survey_analysis_retry,
            )

            SurveyAnalysisService.process_recipient_post_call(
                db,
                order=order,
                recipient=recipient,
                terminal_status=terminal,
                hangup_extra=hangup_extra,
            )
            if terminal == "completed" and not str(hangup_extra.get("transcript") or "").strip():
                schedule_survey_analysis_retry(order.id, recipient.id)
        except Exception:
            logger.exception("survey_post_call_analysis_failed")

        _log(
            "call_ended",
            order_id=order.id,
            recipient_id=recipient.id,
            status=terminal,
            call_control_id=call_id,
        )
        return True

    return False


def process_due_survey_call_orders(db: Session) -> int:
    return SurveyCallDispatchService.process_due_orders(db)


async def survey_call_scheduler_loop(stop_event: asyncio.Event) -> None:
    from app.core.database import get_sessionmaker
    from app.services.survey_analysis_service import SurveyAnalysisService

    sessionmaker = get_sessionmaker()
    while not stop_event.is_set():
        try:
            with sessionmaker() as db:
                count = process_due_survey_call_orders(db)
                if count:
                    logger.info("survey_call_campaigns_started", extra={"count": count})
                SurveyAnalysisService.process_pending_analysis(db)
        except Exception:
            logger.exception("survey_call_scheduler_tick_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            continue
