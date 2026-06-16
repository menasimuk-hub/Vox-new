"""Send approved Customer Feedback WhatsApp templates via Telnyx."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackLocation, FeedbackWaTemplate
from app.services.customer_feedback.feedback_telnyx_push_service import (
    _feedback_template_meta_context,
    english_anchor_template,
    feedback_meta_template_name,
    normalize_feedback_language,
)
from app.services.customer_feedback.survey_config_service import format_template_message
from app.services.telnyx_messaging_service import TelnyxMessageResult, TelnyxMessagingService

logger = logging.getLogger(__name__)

_APPROVED_SYNC_STATUSES = frozenset({"approved", "synced", "live"})


class FeedbackWaSendService:
    @staticmethod
    def resolve_meta_template_name(db: Session, tpl: FeedbackWaTemplate) -> str:
        industry_slug, survey_slug = _feedback_template_meta_context(db, tpl)
        anchor = english_anchor_template(db, tpl)
        return feedback_meta_template_name(
            tpl,
            industry_slug=industry_slug,
            survey_type_slug=survey_slug,
            name_anchor_id=anchor.id,
        )

    @staticmethod
    def _language_candidates(tpl: FeedbackWaTemplate) -> list[str]:
        primary = normalize_feedback_language(tpl.language)
        langs: list[str] = []
        for candidate in (primary, "en_GB", "en_US", "en", "ar"):
            code = str(candidate or "").strip()
            if code and code not in langs:
                langs.append(code)
        return langs or ["en_GB"]

    @staticmethod
    def send_template(
        db: Session,
        *,
        to_number: str,
        org_id: str | None,
        tpl: FeedbackWaTemplate,
        location: FeedbackLocation | None = None,
    ) -> TelnyxMessageResult:
        _ = location  # Meta template names come from the template row, not the QR location.
        sync_status = str(tpl.telnyx_sync_status or "").lower()
        if sync_status not in _APPROVED_SYNC_STATUSES:
            logger.warning(
                "feedback_wa_template_not_approved template_id=%s template_key=%s status=%s",
                tpl.id,
                tpl.template_key,
                sync_status or "draft",
            )

        meta_name = FeedbackWaSendService.resolve_meta_template_name(db, tpl)
        rendered_body = format_template_message(tpl)
        langs = FeedbackWaSendService._language_candidates(tpl)

        result: TelnyxMessageResult | None = None
        for lang in langs:
            attempt = TelnyxMessagingService.send_whatsapp(
                db,
                to_number=to_number,
                body=rendered_body,
                template_name=meta_name,
                template_language=lang,
                org_id=org_id,
                meter_usage=False,
            )
            result = attempt
            if attempt.ok:
                logger.info(
                    "feedback_wa_template_sent to=%s template_key=%s meta_name=%s language=%s",
                    to_number,
                    tpl.template_key,
                    meta_name,
                    lang,
                )
                return attempt

        logger.warning(
            "feedback_wa_template_send_failed to=%s template_key=%s meta_name=%s status=%s detail=%s",
            to_number,
            tpl.template_key,
            meta_name,
            result.status if result else "failed",
            result.detail if result else "no attempt",
        )
        return result or TelnyxMessageResult(
            ok=False,
            status="failed",
            detail="WhatsApp template send failed",
            channel="whatsapp",
        )

    @staticmethod
    def send_plain_or_template(
        db: Session,
        *,
        to_number: str,
        body: str,
        org_id: str | None,
        tpl: FeedbackWaTemplate | None = None,
        location: FeedbackLocation | None = None,
        require_template: bool = False,
    ) -> TelnyxMessageResult:
        if tpl is not None:
            return FeedbackWaSendService.send_template(
                db,
                to_number=to_number,
                org_id=org_id,
                tpl=tpl,
                location=location,
            )
        if require_template:
            logger.error(
                "feedback_wa_template_required to=%s org_id=%s body=%r",
                to_number,
                org_id,
                str(body or "")[:120],
            )
            return TelnyxMessageResult(
                ok=False,
                status="missing_template",
                detail="No approved WhatsApp template matched this feedback step.",
                channel="whatsapp",
            )
        logger.warning(
            "feedback_wa_plain_text_fallback to=%s org_id=%s body=%r",
            to_number,
            org_id,
            str(body or "")[:120],
        )
        return TelnyxMessagingService.send_whatsapp(
            db,
            to_number=to_number,
            body=body,
            org_id=org_id,
            meter_usage=False,
        )
