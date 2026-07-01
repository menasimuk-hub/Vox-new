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
from app.utils.ofcom import now_uk, org_calling_allowed

logger = get_logger(__name__)

LOG_PREFIX = "[survey-call]"

VOICE_PENDING = {"pending", ""}
VOICE_TERMINAL = {"completed", "no_answer", "failed", "busy", "skipped", "cancelled", "opted_out"}
VOICE_ACTIVE = {"calling"}


def _log(event: str, **detail: Any) -> None:
    logger.info("%s %s", LOG_PREFIX, event, extra=detail)


def get_survey_telnyx_assistant_id(db: Session, order: ServiceOrder | None = None) -> str:
    """Backward-compatible helper; prefer resolve_survey_telnyx_assistant_id with order context."""
    if order is not None:
        from app.services.survey_voice_agent_service import resolve_survey_telnyx_assistant_id

        assistant_id, _agent = resolve_survey_telnyx_assistant_id(db, order, _order_config(order))
        return assistant_id
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


def _persist_schedule_block_reason(db: Session, order: ServiceOrder, reason: str) -> None:
    config = _order_config(order)
    config["last_schedule_block_reason"] = str(reason or "").strip() or "Survey could not start"
    config["last_schedule_block_at"] = datetime.utcnow().isoformat()
    order.config_json = json.dumps(config, ensure_ascii=False)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)


def _clear_schedule_block_reason(db: Session, order: ServiceOrder) -> None:
    config = _order_config(order)
    if "last_schedule_block_reason" not in config and "last_schedule_block_at" not in config:
        return
    config.pop("last_schedule_block_reason", None)
    config.pop("last_schedule_block_at", None)
    order.config_json = json.dumps(config, ensure_ascii=False)
    db.add(order)
    db.commit()


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
    """Legacy helper for tests — prefer build_survey_runtime_instructions with agent config."""
    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "the organisation").strip()
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
    first = _first_name(recipient_name)
    system = str(config.get("system_prompt") or "").strip()
    script = str(config.get("approved_script") or "").strip()
    goal = str(config.get("goal") or "").strip()
    workflow = str(config.get("call_workflow") or "").strip()

    parts: list[str] = []
    if system:
        parts.append(system)
    else:
        parts.append(
            "You are conducting a short outbound phone survey on behalf of the client's organisation. "
            "Be warm, concise, and professional. Ask the survey questions clearly and listen to answers."
        )
    if workflow:
        parts.append(f"Call workflow:\n{workflow}")
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


def _order_window_ok(db: Session, order: ServiceOrder, *, now: datetime | None = None) -> tuple[bool, str | None]:
    now = now or datetime.utcnow()
    if order.scheduled_start_at and now < order.scheduled_start_at:
        return False, "Survey calling window has not started"
    if order.scheduled_end_at and now >= order.scheduled_end_at:
        return False, "Survey calling window has ended"
    allowed, reason = org_calling_allowed(db, order.org_id, now=now_uk())
    if not allowed:
        return False, reason or "Outside calling hours"
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
        from app.services.crm_deal_survey_automation_service import survey_crm_automation_blocks_auto_complete

        if survey_crm_automation_blocks_auto_complete(order):
            return order
        was_completed = str(order.status or "").lower() == "completed"
        order.status = "completed"
        order.completed_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        _log("order_completed", order_id=order.id)
        if not was_completed:
            from app.services.notification_service import NotificationService

            NotificationService.create_campaign_completed_notification(db, order=order)
            db.commit()
            try:
                from app.services.billing_reconciliation_service import BillingReconciliationService

                BillingReconciliationService.on_order_terminal(db, order, trigger="completion")
            except Exception:
                import logging

                logging.getLogger(__name__).exception(
                    "survey_billing_terminal_failed order_id=%s", order.id
                )
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
    was_completed = str(order.status or "").lower() == "completed"
    order.status = "completed"
    order.completed_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    _log("order_window_ended", order_id=order.id, reason=reason)
    if not was_completed:
        from app.services.notification_service import NotificationService

        NotificationService.create_campaign_completed_notification(db, order=order)
        db.commit()
        try:
            from app.services.billing_reconciliation_service import BillingReconciliationService

            BillingReconciliationService.on_order_terminal(db, order, trigger="completion")
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "survey_window_billing_terminal_failed order_id=%s", order.id
            )
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
            try:
                if is_ai_call_survey_order(order):
                    if SurveyCallDispatchService.start_campaign(db, order):
                        started += 1
                    continue
                from app.services.survey_whatsapp_conversation_service import is_whatsapp_survey_order

                if is_whatsapp_survey_order(order):
                    ServiceOrderService.start_order(db, order)
                    started += 1
            except Exception as exc:
                _log("start_failed", order_id=order.id, error=str(exc))
                logger.exception("survey_start_failed")

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

        config = _order_config(order)
        from app.services.survey_voice_agent_service import resolve_survey_telnyx_assistant_id

        assistant_id, agent = resolve_survey_telnyx_assistant_id(db, order, config)
        if not assistant_id:
            _log("assistant_missing", order_id=order.id)
            _persist_schedule_block_reason(db, order, "Telnyx voice assistant is not configured")
            return False
        from app.services.script_moderation_service import script_moderation_blocks_launch

        moderation_block = script_moderation_blocks_launch(config)
        if moderation_block:
            _log("script_moderation_blocked", order_id=order.id, reason=moderation_block)
            _persist_schedule_block_reason(db, order, moderation_block)
            return False
        if not config.get("script_approved") and not str(config.get("approved_script") or "").strip():
            _log("script_not_approved", order_id=order.id)
            _persist_schedule_block_reason(db, order, "Survey script is not approved")
            return False

        ok, reason = _order_window_ok(db, order)
        if not ok:
            _log("window_blocked_at_start", order_id=order.id, reason=reason)
            _persist_schedule_block_reason(db, order, reason or "Outside calling window or hours")
            return False

        from app.services.survey_voice_agent_service import clear_survey_generated_script_on_launch

        if agent:
            config["agent_id"] = agent.id
            config["agent_voice_label"] = agent.voice_label or agent.name
        runtime_script = str(config.get("approved_script") or config.get("generated_script_draft") or "").strip()
        if runtime_script:
            config["survey_runtime_prompt"] = runtime_script
        config = clear_survey_generated_script_on_launch(config)
        order.config_json = json.dumps(config, ensure_ascii=False)
        db.add(order)
        db.commit()
        db.refresh(order)
        if agent:
            _log("agent_assigned", order_id=order.id, agent_id=agent.id, voice_label=config.get("agent_voice_label"))

        now = datetime.utcnow()
        _clear_schedule_block_reason(db, order)
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
        ok, reason = _order_window_ok(db, order)
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

        config = _order_config(order)
        from app.services.survey_voice_agent_service import (
            build_survey_opening_greeting,
            build_survey_runtime_instructions,
            resolve_survey_telnyx_assistant_id,
            should_skip_recipient_for_opt_out,
            should_wait_for_retry,
        )

        assistant_id, agent = resolve_survey_telnyx_assistant_id(db, order, config)
        if not assistant_id:
            return None

        ok, reason = _order_window_ok(db, order)
        if not ok:
            _complete_order_window_expired(db, order, reason=reason or "window_ended")
            return None

        recipients = ServiceOrderService.get_recipients(db, order.id)
        if _any_recipient_calling(recipients):
            return None

        next_recipient = None
        for candidate in recipients:
            status = str(candidate.status or "pending").lower()
            if status not in VOICE_PENDING:
                continue
            if should_skip_recipient_for_opt_out(candidate):
                continue
            from app.services.org_opt_out_service import OrgOptOutService

            if OrgOptOutService.is_phone_opted_out(db, order.org_id, str(candidate.phone or "")):
                continue
            if should_wait_for_retry(candidate):
                continue
            from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

            phone_check = TelnyxPhoneAllowlistService.validate_phone_db(db, str(candidate.phone or ""))
            if not phone_check.get("allowed"):
                continue
            next_recipient = candidate
            break
        if next_recipient is None:
            _finalize_order_if_done(db, order)
            return None

        return SurveyCallDispatchService._dial_recipient(db, order, next_recipient, agent=agent, assistant_id=assistant_id)

    @staticmethod
    def dial_recipient(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        *,
        retry: bool = False,
    ) -> ServiceOrderRecipient:
        if order.status != "running":
            raise ValueError("Survey must be running before placing AI calls")
        if recipient.order_id != order.id:
            raise ValueError("Contact does not belong to this survey")

        config = _order_config(order)
        from app.services.survey_voice_agent_service import resolve_survey_telnyx_assistant_id

        assistant_id, agent = resolve_survey_telnyx_assistant_id(db, order, config)
        if not assistant_id:
            raise ValueError("Survey voice agent is not configured")

        ok, reason = _order_window_ok(db, order)
        if not ok:
            raise ValueError(reason or "Outside the survey calling window")

        recipients = ServiceOrderService.get_recipients(db, order.id)
        if _any_recipient_calling(recipients):
            active = next((r for r in recipients if str(r.status or "").lower() == "calling"), None)
            if active and active.id != recipient.id:
                raise ValueError("Another contact is already being called")

        status = str(recipient.status or "pending").lower()
        if status == "calling":
            raise ValueError("This contact is already being called")
        if status == "completed" and not retry:
            raise ValueError("Contact already completed — use call again to retry")
        if retry and status in VOICE_TERMINAL:
            recipient.status = "pending"
            db.add(recipient)
            db.commit()
            db.refresh(recipient)

        row = SurveyCallDispatchService._dial_recipient(db, order, recipient, agent=agent, assistant_id=assistant_id)
        if row is None:
            raise ValueError("Could not place AI call")
        return row

    @staticmethod
    def _dial_recipient(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        *,
        agent,
        assistant_id: str,
    ) -> ServiceOrderRecipient | None:
        config = _order_config(order)
        from app.services.survey_voice_agent_service import (
            build_survey_opening_greeting,
            build_survey_runtime_instructions,
        )

        telnyx_config = _telnyx_config(db)
        from_number = telnyx_outbound_caller_id(telnyx_config)
        if not from_number:
            _log("caller_id_missing", order_id=order.id)
            return None

        instructions = build_survey_runtime_instructions(
            db, order=order, config=config, recipient=recipient, agent=agent
        )
        greeting = build_survey_opening_greeting(
            db, agent=agent, config=config, recipient_name=recipient.name, org_id=order.org_id
        )
        voicemail_behavior = _resolve_voicemail_behavior({}, agent)
        from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

        phone_check = TelnyxPhoneAllowlistService.validate_phone_db(db, str(recipient.phone or ""))
        if not phone_check.get("allowed"):
            now = datetime.utcnow()
            recipient.status = "failed"
            _set_recipient_result(
                db,
                recipient,
                {
                    "channel": "ai_call",
                    "error": phone_check.get("reason") or "Phone number not allowed",
                    "failed_at": now.isoformat(),
                    "phone_call_block_reason": phone_check.get("reason"),
                },
            )
            _refresh_order_report(db, order)
            _log("dial_blocked_allowlist", order_id=order.id, recipient_id=recipient.id, detail=phone_check.get("reason"))
            return None

        to_number = normalize_telnyx_e164(str(recipient.phone or ""))

        result = TelnyxVoiceAdapter.start_outbound_call(
            to_number=to_number,
            from_number=from_number,
            config=telnyx_config,
            client_state={
                "survey_call": True,
                "service_order_id": order.id,
                "recipient_id": recipient.id,
                "org_id": order.org_id,
                "agent_id": agent.id if agent else None,
                "telnyx_assistant_id": assistant_id,
                "survey_greeting": greeting,
                "survey_instructions": instructions[:4000],
                "voicemail_behavior": voicemail_behavior,
            },
        )

        now = datetime.utcnow()
        if not result.ok or not result.external_id:
            recipient.status = "failed"
            _set_recipient_result(
                db,
                recipient,
                {
                    "channel": "ai_call",
                    "error": result.detail or result.status or "dial_failed",
                    "failed_at": now.isoformat(),
                },
            )
            _refresh_order_report(db, order)
            _log("dial_failed", order_id=order.id, recipient_id=recipient.id, detail=result.detail)
            return recipient

        recipient.status = "calling"
        _set_recipient_result(
            db,
            recipient,
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
            recipient_id=recipient.id,
            call_control_id=result.external_id,
        )
        return recipient

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
        secs = payload.get("duration_seconds")
        try:
            secs_int = int(secs) if secs is not None else None
        except (TypeError, ValueError):
            secs_int = None
        if secs_int is not None:
            from app.services.billing_call_minutes import billable_call_minutes, call_outcome_label

            payload["billable_minutes"] = billable_call_minutes(secs_int)
            payload["call_type"] = call_outcome_label(
                status=status,
                hangup_cause=str(payload.get("hangup_cause") or ""),
            )
        merged = _recipient_result(recipient)
        merged.update(payload)
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        db.refresh(recipient)
        _refresh_order_report(db, order)

        recipients = ServiceOrderService.get_recipients(db, order.id)
        if order.status == "running" and not _any_recipient_calling(recipients):
            ok, reason = _order_window_ok(db, order)
            if not ok:
                _complete_order_window_expired(db, order, reason=reason or "window_ended")
            elif _all_recipients_terminal(recipients):
                _finalize_order_if_done(db, order)
            else:
                SurveyCallDispatchService.dial_next_recipient(db, order)


_VOICEMAIL_BEHAVIORS = frozenset({"hang_up", "leave_message", "retry_later"})


def _resolve_voicemail_behavior(parsed: dict[str, Any], agent) -> str:
    behavior = str(parsed.get("voicemail_behavior") or "").strip().lower()
    if behavior in _VOICEMAIL_BEHAVIORS:
        return behavior
    if agent is not None:
        behavior = str(getattr(agent, "voicemail_behavior", None) or "").strip().lower()
        if behavior in _VOICEMAIL_BEHAVIORS:
            return behavior
    return "hang_up"


def _is_voicemail_telnyx_event(event_type: str, record: dict[str, Any]) -> bool:
    et = str(event_type or "").lower()
    if "machine" in et and ("detection" in et or "detected" in et):
        result = str(
            record.get("result")
            or record.get("machine_detection_result")
            or record.get("machine_detection")
            or ""
        ).lower()
        if result in {"machine", "fax", "voicemail", "answering_machine"}:
            return True
        if "ended" in et and result and result not in {"human", "not_sure", "unknown", ""}:
            return True
    hangup_cause = str(record.get("hangup_cause") or record.get("sip_hangup_cause") or "").lower()
    return any(token in hangup_cause for token in ("machine", "answering_machine", "voicemail"))


def _voicemail_message(config: dict[str, Any], *, recipient_name: str, agent) -> str:
    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "the organisation").strip()
    first = _first_name(recipient_name)
    agent_name = str(getattr(agent, "voice_label", None) or getattr(agent, "name", None) or "your AI assistant").strip()
    return (
        f"Hi {first}, this is {agent_name} calling from {org_name} with a brief survey request. "
        "We'll try again later. Thank you."
    )


def _handle_survey_voicemail(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    call_id: str,
    parsed: dict[str, Any],
    agent,
    config_order: dict[str, Any],
    telnyx_config: dict[str, Any],
    assistant_id: str,
    behavior: str,
) -> bool:
    """Apply agent voicemail policy. Returns True when the event is fully handled."""
    behavior = behavior if behavior in _VOICEMAIL_BEHAVIORS else "hang_up"
    extra = {
        "call_control_id": call_id,
        "voicemail_detected": True,
        "voicemail_behavior": behavior,
    }

    if behavior == "leave_message" and assistant_id:
        greeting = _voicemail_message(config_order, recipient_name=recipient.name, agent=agent)
        instructions = (
            "You reached voicemail. Leave ONLY this brief message, then end the call immediately. "
            "Do not ask survey questions.\n\n"
            f"Message to leave:\n{greeting}"
        )
        result = TelnyxVoiceAdapter.start_ai_assistant(
            call_control_id=call_id,
            assistant_id=assistant_id,
            config=telnyx_config,
            instructions=instructions,
            greeting=greeting,
            prepared=False,
        )
        if result.ok:
            _set_recipient_result(
                db,
                recipient,
                {
                    **extra,
                    "voicemail_message_started_at": datetime.utcnow().isoformat(),
                    "assistant_status": result.status,
                },
            )
            _log("voicemail_message_started", order_id=order.id, recipient_id=recipient.id, call_control_id=call_id)
            return True
        extra["error"] = result.detail or result.status

    TelnyxVoiceAdapter.hangup_call(call_control_id=call_id, config=telnyx_config)
    SurveyCallDispatchService.finalize_recipient_after_call(
        db,
        order=order,
        recipient=recipient,
        status="no_answer",
        extra=extra,
    )
    if behavior == "retry_later":
        try:
            from app.services.survey_voice_agent_service import resolve_survey_retry_settings, schedule_recipient_retry

            max_retries, delay_seconds = resolve_survey_retry_settings(db, order)
            schedule_recipient_retry(db, recipient, delay_seconds=delay_seconds, max_retries=max_retries)
            _log("voicemail_retry_scheduled", order_id=order.id, recipient_id=recipient.id)
        except Exception:
            logger.exception("survey_voicemail_retry_failed")
    _log("voicemail_hung_up", order_id=order.id, recipient_id=recipient.id, behavior=behavior, call_control_id=call_id)
    return True


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

    assistant_id = str(parsed.get("telnyx_assistant_id") or get_survey_telnyx_assistant_id(db, order) or "").strip()
    telnyx_config = _telnyx_config(db)
    config_order = _order_config(order)
    from app.services.survey_voice_agent_service import resolve_survey_agent_for_order

    agent = resolve_survey_agent_for_order(db, order, config_order)
    voicemail_behavior = _resolve_voicemail_behavior(parsed, agent)

    if _is_voicemail_telnyx_event(event_type, record):
        return _handle_survey_voicemail(
            db,
            order=order,
            recipient=recipient,
            call_id=call_id,
            parsed=parsed,
            agent=agent,
            config_order=config_order,
            telnyx_config=telnyx_config,
            assistant_id=assistant_id,
            behavior=voicemail_behavior,
        )

    if "answered" in event_type:
        from app.services.survey_voice_agent_service import (
            build_survey_opening_greeting,
            build_survey_runtime_instructions,
        )

        instructions = str(parsed.get("survey_instructions") or "").strip() or build_survey_runtime_instructions(
            db,
            order=order,
            config=config_order,
            recipient=recipient,
            agent=agent,
        )
        greeting = str(parsed.get("survey_greeting") or "").strip() or build_survey_opening_greeting(
            db,
            agent=agent,
            config=config_order,
            recipient_name=recipient.name,
            org_id=order.org_id,
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
            config=telnyx_config,
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
        prior = _recipient_result(recipient)
        if (
            _is_voicemail_telnyx_event(event_type, record)
            and not prior.get("assistant_started_at")
            and not prior.get("voicemail_message_started_at")
            and str(recipient.status or "").lower() == "calling"
        ):
            return _handle_survey_voicemail(
                db,
                order=order,
                recipient=recipient,
                call_id=call_id,
                parsed=parsed,
                agent=agent,
                config_order=config_order,
                telnyx_config=telnyx_config,
                assistant_id=assistant_id,
                behavior=voicemail_behavior,
            )

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

        from app.services.survey_voice_agent_service import (
            detect_opt_out_text,
            mark_recipient_opted_out,
            schedule_recipient_retry,
        )

        if transcript and detect_opt_out_text(transcript):
            mark_recipient_opted_out(db, recipient, source_text=transcript)
            _log("recipient_opted_out", order_id=order.id, recipient_id=recipient.id)
            try:
                from app.services.survey_analysis_service import SurveyAnalysisService

                SurveyAnalysisService.process_recipient_post_call(
                    db,
                    order=order,
                    recipient=recipient,
                    terminal_status="opted_out",
                    hangup_extra=hangup_extra,
                )
            except Exception:
                logger.exception("survey_opt_out_analysis_failed")
            return True

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

        if terminal in {"no_answer", "busy"} and str(recipient.status or "").lower() != "opted_out":
            try:
                from app.services.survey_voice_agent_service import resolve_survey_retry_settings

                max_retries, delay_seconds = resolve_survey_retry_settings(db, order)
                schedule_recipient_retry(db, recipient, delay_seconds=delay_seconds, max_retries=max_retries)
                _log("recipient_retry_scheduled", order_id=order.id, recipient_id=recipient.id, status=terminal)
            except Exception:
                logger.exception("survey_recipient_retry_failed")

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

    from app.services.scheduler_lock import is_scheduler_leader

    sessionmaker = get_sessionmaker()
    while not stop_event.is_set():
        try:
            if is_scheduler_leader():
                with sessionmaker() as db:
                    count = process_due_survey_call_orders(db)
                    if count:
                        logger.info("survey_call_campaigns_started", extra={"count": count})
                    SurveyAnalysisService.process_pending_analysis(db)
                    from app.services.survey_wa_final_feedback_service import process_final_feedback_timeouts

                    timed_out = process_final_feedback_timeouts(db)
                    if timed_out:
                        logger.info("survey_final_feedback_timeouts", extra={"count": timed_out})
        except Exception:
            logger.exception("survey_call_scheduler_tick_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            continue
