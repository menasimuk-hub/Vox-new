"""Deliver graph survey outcomes over WhatsApp (P3) — template send with safe fallback."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.services.survey_dispatch_service import _first_name, _personalize
from app.services.survey_flow_config_service import is_simulator_dry_run
from app.services.survey_flow_constants import ACTION_SEND_TEMPLATE, ACTION_SEND_TEXT
from app.services.survey_wa_pacing_service import PACING_STEP, pause_before_outbound
from app.services.survey_outcome_delivery_schema import (
    build_outcome_delivery_record,
    dumps_outcome_delivery,
    loads_outcome_delivery,
)
from app.services.survey_session_service import SurveySessionService
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)
LOG_PREFIX = "[survey-outcome]"


class SurveyOutcomeSendService:
    @staticmethod
    def already_delivered(session: SurveySession) -> bool:
        delivery = loads_outcome_delivery(session.outcome_delivery_json)
        return bool(delivery.get("sent_at"))

    @staticmethod
    def deliver(
        db: Session,
        *,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        session: SurveySession,
        outcome_result: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        WhatsApp-only outcome delivery. Idempotent per session.
        Template send failure falls back to personalized text on WhatsApp (no SMS).
        """
        if SurveyOutcomeSendService.already_delivered(session):
            delivery = loads_outcome_delivery(session.outcome_delivery_json)
            logger.info(
                "%s idempotent_skip session=%s outcome=%s",
                LOG_PREFIX,
                session.id,
                delivery.get("outcome_key"),
            )
            out = {"ok": True, "skipped": True, "detail": "outcome_already_sent", **delivery}
            out["skipped"] = True
            return out

        org_name = str(config.get("organisation_name") or config.get("clinic_name") or "Your business").strip()
        organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
        first = _first_name(recipient.name)

        action_type = str(outcome_result.get("action_type") or ACTION_SEND_TEXT)
        template_send = outcome_result.get("template_send")
        force_template_fail = bool(config.get("simulator_force_template_fail"))
        fallback_body = _personalize(
            str(outcome_result.get("body") or outcome_result.get("message_body") or "Thank you for your feedback."),
            first_name=first,
            org_name=org_name,
            organiser=organiser,
        )

        channel = "whatsapp"
        detail = ""
        external_id = None
        ok = False
        used_fallback = False
        template_send_failed = False
        result = None
        dry_run = is_simulator_dry_run(config)

        if dry_run:
            used_fallback = (
                force_template_fail
                and action_type == ACTION_SEND_TEMPLATE
                and isinstance(template_send, dict)
                and template_send.get("telnyx_template_id")
            ) or action_type == ACTION_SEND_TEXT or not template_send
            ok = True
            detail = "simulated_text_fallback" if used_fallback else "simulated_template_send"
            if used_fallback and action_type == ACTION_SEND_TEMPLATE:
                detail = "simulated_template_failure_fallback"
            external_id = "simulator-dry-run"
        elif action_type == ACTION_SEND_TEMPLATE and isinstance(template_send, dict) and template_send.get("telnyx_template_id"):
            pause_before_outbound(
                pacing=PACING_STEP,
                order_id=order.id,
                recipient_id=recipient.id,
                skip=dry_run,
            )
            components = template_send.get("components")
            try:
                result = TelnyxMessagingService.send_whatsapp(
                    db,
                    org_id=order.org_id,
                    to_number=recipient.phone or "",
                    body=fallback_body,
                    template_id=str(template_send.get("telnyx_template_id") or ""),
                    template_name=str(template_send.get("template_name") or ""),
                    template_language=str(template_send.get("language") or "en_US"),
                    template_components=components if isinstance(components, list) else None,
                    meter_usage=False,
                )
                ok = bool(result.ok)
                detail = result.detail or ""
                external_id = result.external_id
                channel = result.channel or "whatsapp"
            except Exception as exc:
                template_send_failed = True
                logger.warning(
                    "%s template_send_failed session=%s order=%s template=%s err=%s",
                    LOG_PREFIX,
                    session.id,
                    order.id,
                    template_send.get("template_id"),
                    exc,
                )
                ok = False
                detail = str(exc)

            if not ok:
                used_fallback = True
                if action_type == ACTION_SEND_TEMPLATE:
                    template_send_failed = True
                pause_before_outbound(
                    pacing=PACING_STEP,
                    order_id=order.id,
                    recipient_id=recipient.id,
                    skip=dry_run,
                )
                result = TelnyxMessagingService.send_whatsapp(
                    db,
                    org_id=order.org_id,
                    to_number=recipient.phone or "",
                    body=fallback_body,
                    meter_usage=False,
                )
                ok = bool(result.ok)
                detail = f"template_fallback: {detail}; {result.detail or ''}"
                external_id = result.external_id
                channel = result.channel or "whatsapp"
        else:
            pause_before_outbound(
                pacing=PACING_STEP,
                order_id=order.id,
                recipient_id=recipient.id,
                skip=dry_run,
            )
            result = TelnyxMessagingService.send_whatsapp(
                db,
                org_id=order.org_id,
                to_number=recipient.phone or "",
                body=fallback_body,
                meter_usage=False,
            )
            ok = bool(result.ok)
            detail = result.detail or ""
            external_id = result.external_id
            channel = result.channel or "whatsapp"

        try:
            TelnyxMessagingService.log_outbound(
                db,
                org_id=order.org_id,
                to_number=recipient.phone or "",
                from_number=None,
                body=fallback_body[:500],
                result=result,
            )
        except Exception:
            pass

        delivery = build_outcome_delivery_record(
            ok=ok,
            channel=str(channel or "whatsapp"),
            action_type=action_type,
            used_text_fallback=used_fallback or action_type == ACTION_SEND_TEXT,
            template_send_failed=template_send_failed,
            outcome_key=str(outcome_result.get("outcome_key") or ""),
            template_id=outcome_result.get("template_id"),
            detail=str(detail or ""),
            external_id=str(external_id) if external_id else None,
            body_preview=fallback_body[:200],
        )
        session.outcome_delivery_json = dumps_outcome_delivery(delivery)
        logger.info(
            "%s delivered session=%s order=%s ok=%s fallback=%s template_failed=%s outcome=%s",
            LOG_PREFIX,
            session.id,
            order.id,
            ok,
            delivery.get("used_text_fallback"),
            template_send_failed,
            delivery.get("outcome_key"),
        )
        session.updated_at = datetime.utcnow()
        db.add(session)

        SurveySessionService._append_decision(
            db,
            session,
            decision_kind="outcome_action",
            rule_key=f"outcome.send.{outcome_result.get('outcome_key') or 'unknown'}",
            from_step=None,
            to_step=None,
            from_role=None,
            to_role=str(outcome_result.get("outcome_key") or ""),
            reason="Outcome message sent via WhatsApp.",
            context=delivery,
        )
        db.commit()

        return {"ok": ok, "sent": ok, **delivery}
