"""Deliver graph survey outcomes over WhatsApp (P3) — template send with safe fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.services.survey_dispatch_service import _first_name, _personalize
from app.services.survey_flow_constants import ACTION_SEND_TEMPLATE, ACTION_SEND_TEXT
from app.services.survey_session_service import SurveySessionService
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)
LOG_PREFIX = "[survey-outcome]"


def _loads_delivery(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class SurveyOutcomeSendService:
    @staticmethod
    def already_delivered(session: SurveySession) -> bool:
        delivery = _loads_delivery(session.outcome_delivery_json)
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
            delivery = _loads_delivery(session.outcome_delivery_json)
            return {"ok": True, "skipped": True, "detail": "outcome_already_sent", **delivery}

        org_name = str(config.get("organisation_name") or config.get("clinic_name") or "Your business").strip()
        organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
        first = _first_name(recipient.name)

        action_type = str(outcome_result.get("action_type") or ACTION_SEND_TEXT)
        template_send = outcome_result.get("template_send")
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
        result = None

        if action_type == ACTION_SEND_TEMPLATE and isinstance(template_send, dict) and template_send.get("telnyx_template_id"):
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
                )
                ok = bool(result.ok)
                detail = result.detail or ""
                external_id = result.external_id
                channel = result.channel or "whatsapp"
            except Exception as exc:
                logger.warning("%s template_send_failed session=%s err=%s", LOG_PREFIX, session.id, exc)
                ok = False
                detail = str(exc)

            if not ok:
                used_fallback = True
                result = TelnyxMessagingService.send_whatsapp(
                    db,
                    org_id=order.org_id,
                    to_number=recipient.phone or "",
                    body=fallback_body,
                )
                ok = bool(result.ok)
                detail = f"template_fallback: {detail}; {result.detail or ''}"
                external_id = result.external_id
                channel = result.channel or "whatsapp"
        else:
            result = TelnyxMessagingService.send_whatsapp(
                db,
                org_id=order.org_id,
                to_number=recipient.phone or "",
                body=fallback_body,
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

        now = datetime.utcnow().isoformat()
        delivery = {
            "sent_at": now,
            "ok": ok,
            "channel": str(channel or "whatsapp"),
            "action_type": action_type,
            "used_text_fallback": used_fallback or action_type == ACTION_SEND_TEXT,
            "outcome_key": str(outcome_result.get("outcome_key") or ""),
            "template_id": outcome_result.get("template_id"),
            "detail": str(detail or "")[:500],
            "external_id": str(external_id) if external_id else None,
            "body_preview": fallback_body[:200],
        }
        session.outcome_delivery_json = json.dumps(delivery, ensure_ascii=False)
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
