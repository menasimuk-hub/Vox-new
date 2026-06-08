"""Step 5 WA survey builder test — stateful session, not bulk template blast."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.core.runtime_build_info import log_wa_test_session_persistence_fix_active
from app.services.messaging_log_service import normalize_e164
from app.services.platform_catalog_service import ServiceOrderService
from app.services.survey_session_service import SurveySessionPersistenceError, SurveySessionService
from app.services.survey_wa_test_mode_service import (
    attach_trace_id_to_config,
    log_survey_test,
    new_trace_id,
    persist_trace_id_on_recipient,
)
from app.services.survey_whatsapp_conversation_service import (
    _order_config,
    _recipient_result,
    _save_recipient_result,
    _wa_conversation,
    is_whatsapp_survey_order,
    send_survey_opening,
)
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    _validate_mobile_number,
)

logger = logging.getLogger(__name__)
LOG_PREFIX = "[wa-builder-test]"
# WA_TEST_SESSION_PERSISTENCE_FIX_ACTIVE — fixed Step 5 path: session before welcome (deploy marker)


class SurveyBuilderTestService:
    @staticmethod
    def _supersede_other_active_surveys(
        db: Session,
        *,
        org_id: str,
        phone: str,
        keep_order_id: str,
    ) -> None:
        from app.services.survey_whatsapp_conversation_service import _phone_candidates

        needles = _phone_candidates(phone)
        if not needles:
            return
        orders = list(
            db.execute(
                select(ServiceOrder).where(
                    ServiceOrder.org_id == org_id,
                    ServiceOrder.service_code == "survey",
                    ServiceOrder.status.in_(("running", "draft")),
                )
            ).scalars()
        )
        now = datetime.utcnow()
        for order in orders:
            if str(order.id) == keep_order_id:
                continue
            if not is_whatsapp_survey_order(order):
                continue
            for recipient in ServiceOrderService.get_recipients(db, order.id):
                if str(recipient.status or "").lower() in {"completed", "cancelled", "opted_out"}:
                    continue
                rec_phones = _phone_candidates(recipient.phone or "")
                if not needles.intersection(rec_phones):
                    continue
                session = SurveySessionService.get_active_by_recipient(db, recipient.id)
                if session is not None:
                    session.status = "completed"
                    session.completed_at = now
                    session.updated_at = now
                    db.add(session)
                recipient.status = "cancelled"
                recipient.updated_at = now
                payload = _recipient_result(recipient)
                conv = _wa_conversation(payload)
                conv["cancelled_at"] = now.isoformat()
                conv["cancel_reason"] = "superseded_by_builder_test"
                payload["wa_conversation"] = conv
                recipient.result_json = json.dumps(payload, ensure_ascii=False)
                db.add(recipient)
                logger.info(
                    "%s superseded order=%s recipient=%s for phone=%s",
                    LOG_PREFIX,
                    order.id,
                    recipient.id,
                    phone,
                )
        db.commit()

    @staticmethod
    def _merge_test_config(
        config: dict[str, Any],
        *,
        first_name: str,
        business_name: str,
    ) -> dict[str, Any]:
        from app.services.survey_builder_flow_service import effective_order_config

        merged = effective_order_config(dict(config))
        merged["delivery"] = "whatsapp"
        merged["survey_channel"] = "whatsapp"
        merged.setdefault("channels", ["whatsapp"])
        merged["wa_builder_test"] = True
        merged["test_mode"] = True
        if business_name:
            merged["organisation_name"] = business_name
            merged.setdefault("client_name", business_name)
        if first_name:
            merged["test_first_name"] = first_name
        return merged

    @staticmethod
    def _validate_survey_config(config: dict[str, Any]) -> None:
        wa_flow = config.get("whatsapp_flow")
        if not isinstance(wa_flow, dict):
            raise SurveyWhatsappTemplateError(
                "Survey is not generated yet. Complete Step 3 (Generate) before sending a test."
            )
        questions = (
            config.get("builder_runtime", {}).get("step_sequence")
            if isinstance(config.get("builder_runtime"), dict)
            else None
        ) or config.get("builder_step_sequence") or wa_flow.get("questions")
        if not isinstance(questions, list) or not questions:
            raise SurveyWhatsappTemplateError(
                "Survey has no frozen builder step sequence — click Generate again in Step 3."
            )
        if not config.get("wa_template_id"):
            raise SurveyWhatsappTemplateError("Welcome template is missing — regenerate in Step 3.")

    @staticmethod
    def start_wa_test_session(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        order_id: str,
        test_phone: str,
        first_name: str = "Alex",
        business_name: str = "Your business",
    ) -> dict[str, Any]:
        """Create/update a running survey session and send only the welcome template."""
        logger.info(
            "%s start org=%s user=%s order=%s phone=%s",
            LOG_PREFIX,
            org_id,
            user_id,
            order_id,
            test_phone,
        )
        recipient_e164, phone_error = _validate_mobile_number(test_phone)
        if phone_error or not recipient_e164:
            raise SurveyWhatsappTemplateError(phone_error or "Enter a valid mobile number in E.164 format.")

        order = db.get(ServiceOrder, str(order_id or "").strip())
        if order is None or str(order.org_id) != str(org_id):
            raise SurveyWhatsappTemplateError("Survey order not found.")
        if order.service_code != "survey":
            raise SurveyWhatsappTemplateError("Order is not a survey.")

        config = _order_config(order)
        SurveyBuilderTestService._validate_survey_config(config)
        config = SurveyBuilderTestService._merge_test_config(
            config,
            first_name=first_name,
            business_name=business_name,
        )
        trace_id = new_trace_id()
        config = attach_trace_id_to_config(config, trace_id)

        SurveyBuilderTestService._supersede_other_active_surveys(
            db,
            org_id=org_id,
            phone=recipient_e164,
            keep_order_id=order.id,
        )

        now = datetime.utcnow()
        order.config_json = json.dumps(config, ensure_ascii=False)
        order.status = "running"
        order.started_at = order.started_at or now
        order.scheduled_start_at = order.scheduled_start_at or (now - timedelta(minutes=1))
        order.scheduled_end_at = order.scheduled_end_at or (now + timedelta(days=7))
        order.updated_at = now
        db.add(order)
        db.commit()
        db.refresh(order)
        logger.info("%s order running order_id=%s", LOG_PREFIX, order.id)

        recipient: ServiceOrderRecipient | None = None
        for row in ServiceOrderService.get_recipients(db, order.id):
            try:
                if normalize_e164(row.phone or "") == normalize_e164(recipient_e164):
                    recipient = row
                    break
            except ValueError:
                if str(row.phone or "").strip() == recipient_e164:
                    recipient = row
                    break

        if recipient is None:
            next_row = len(ServiceOrderService.get_recipients(db, order.id)) + 1
            recipient = ServiceOrderRecipient(
                order_id=order.id,
                row_number=next_row,
                name=first_name or "Test",
                phone=recipient_e164,
                status="pending",
            )
            db.add(recipient)
            db.commit()
            db.refresh(recipient)
            logger.info("%s created recipient_id=%s", LOG_PREFIX, recipient.id)
        else:
            recipient.name = first_name or recipient.name or "Test"
            recipient.phone = recipient_e164
            recipient.status = "pending"
            recipient.result_json = None
            recipient.updated_at = now
            db.add(recipient)
            db.commit()
            db.refresh(recipient)
            logger.info("%s reset recipient_id=%s", LOG_PREFIX, recipient.id)

        persist_trace_id_on_recipient(recipient, trace_id)
        db.add(recipient)
        db.commit()
        db.refresh(recipient)
        log_survey_test(
            "recipient_resolved",
            trace_id=trace_id,
            order=order,
            recipient=recipient,
            config=config,
            handler="survey_builder_test_service.start_wa_test_session",
            result="ok",
            current_step=0,
        )

        existing_session = SurveySessionService.get_active_by_recipient(db, recipient.id)
        if existing_session is not None:
            existing_session.status = "completed"
            existing_session.completed_at = now
            existing_session.updated_at = now
            db.add(existing_session)
            db.commit()

        from app.services.survey_builder_flow_service import survey_questions_from_config

        questions = survey_questions_from_config(config)
        if not questions:
            raise SurveyWhatsappTemplateError(
                "Survey has no builder step sequence — click Generate again in Step 3."
            )

        logger.info(
            "%s ensure_awaiting_start_session order_id=%s recipient_id=%s phone=%s trace_id=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
            recipient_e164,
            trace_id,
        )
        try:
            pre_session = SurveySessionService.ensure_awaiting_start_session(
                db,
                order=order,
                recipient=recipient,
                config=config,
                question_count=len(questions),
            )
        except Exception as exc:
            log_survey_test(
                "error",
                trace_id=trace_id,
                order=order,
                recipient=recipient,
                config=config,
                handler="survey_builder_test_service.start_wa_test_session",
                result="fail",
                reason="session_ensure_failed",
                extra={"error": str(exc)},
            )
            raise SurveyWhatsappTemplateError(
                f"Could not create awaiting-start session before welcome: {exc}"
            ) from exc

        db.refresh(pre_session)
        try:
            session = SurveySessionService.verify_active_awaiting_start(
                db,
                recipient.id,
                order_id=order.id,
                trace_id=trace_id,
            )
        except SurveySessionPersistenceError as exc:
            raise SurveyWhatsappTemplateError(str(exc)) from exc

        payload_pre = SurveySessionService.attach_session_to_result(_recipient_result(recipient), session)
        _save_recipient_result(db, recipient, payload_pre)
        db.refresh(session)
        log_survey_test(
            "session_created",
            trace_id=trace_id,
            order=order,
            recipient=recipient,
            session=session,
            config=config,
            handler="survey_builder_test_service.start_wa_test_session",
            result="ok",
            current_step=0,
            extra={"phase": "before_welcome_send"},
        )
        log_wa_test_session_persistence_fix_active(
            order_id=str(order.id),
            recipient_id=str(recipient.id),
            session_id=str(session.id),
            trace_id=trace_id,
        )

        logger.info(
            "%s send_survey_opening order_id=%s recipient_id=%s phone=%s session_id=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
            recipient_e164,
            session.id,
        )
        log_survey_test(
            "trace_started",
            trace_id=trace_id,
            order=order,
            recipient=recipient,
            config=config,
            handler="survey_builder_test_service.start_wa_test_session",
            result="ok",
            current_step=0,
            extra={"phone": recipient_e164, "user_id": user_id},
        )
        sent = send_survey_opening(db, order=order, recipient=recipient, config=config)
        db.refresh(recipient)

        try:
            session = SurveySessionService.verify_active_awaiting_start(
                db,
                recipient.id,
                order_id=order.id,
                trace_id=trace_id,
            )
        except SurveySessionPersistenceError as exc:
            raise SurveyWhatsappTemplateError(str(exc)) from exc

        if not sent:
            detail = ""
            try:
                payload = json.loads(recipient.result_json or "{}")
                detail = str(payload.get("error") or payload.get("detail") or "")
            except Exception:
                pass
            raise SurveyWhatsappTemplateError(
                detail or "Could not send the welcome message. Check Telnyx settings and template approval."
            )

        db.refresh(session)
        log_survey_test(
            "welcome_sent",
            trace_id=trace_id,
            order=order,
            recipient=recipient,
            session=session,
            config=config,
            handler="survey_builder_test_service.start_wa_test_session",
            result="ok",
            current_step=0,
        )
        logger.info(
            "%s welcome_sent order_id=%s recipient_id=%s session_id=%s status=%s phone=%s "
            "current_step=%s awaiting_start=true trace_id=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
            session.id,
            session.status,
            recipient_e164,
            int(session.current_step or 0),
            trace_id,
        )

        from app.services.usage_wallet_service import UsageWalletService

        UsageWalletService.record_whatsapp_usage(db, org_id=org_id, units=1, commit=True)
        logger.info("%s test_send_metered org_id=%s units=1", LOG_PREFIX, org_id)

        return {
            "ok": True,
            "success": True,
            "mode": "session",
            "sent": 1,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "session_id": session.id,
            "trace_id": trace_id,
            "status": str(session.status or "active"),
            "to_number": recipient_e164,
            "awaiting_start": True,
            "current_step": int(session.current_step or 0),
            "message": (
                f"Survey test started — welcome message sent to {recipient_e164}. "
                "Reply on WhatsApp to continue the survey step by step."
            ),
        }
