"""Send approved Customer Feedback WhatsApp templates via Telnyx."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackSurveyType, FeedbackWaTemplate
from app.services.customer_feedback.feedback_telnyx_push_service import (
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
    def _resolve_slugs(
        db: Session,
        tpl: FeedbackWaTemplate,
        location: FeedbackLocation | None,
    ) -> tuple[str | None, str | None]:
        industry_slug: str | None = None
        survey_slug: str | None = None

        if location is not None:
            industry = db.get(FeedbackIndustry, location.industry_id)
            industry_slug = industry.slug if industry else None
            survey_type = db.get(FeedbackSurveyType, location.survey_type_id)
            survey_slug = survey_type.slug if survey_type else None
            return industry_slug, survey_slug

        if tpl.industry_id:
            industry = db.get(FeedbackIndustry, tpl.industry_id)
            industry_slug = industry.slug if industry else None
        if tpl.survey_type_id:
            survey_type = db.get(FeedbackSurveyType, tpl.survey_type_id)
            survey_slug = survey_type.slug if survey_type else None
            if survey_type and not industry_slug:
                industry = db.get(FeedbackIndustry, survey_type.industry_id)
                industry_slug = industry.slug if industry else None
        return industry_slug, survey_slug

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
        sync_status = str(tpl.telnyx_sync_status or "").lower()
        if sync_status not in _APPROVED_SYNC_STATUSES:
            logger.warning(
                "feedback_wa_template_not_approved template_id=%s template_key=%s status=%s",
                tpl.id,
                tpl.template_key,
                sync_status or "draft",
            )

        industry_slug, survey_slug = FeedbackWaSendService._resolve_slugs(db, tpl, location)
        anchor = english_anchor_template(db, tpl)
        meta_name = feedback_meta_template_name(
            tpl,
            industry_slug=industry_slug,
            survey_type_slug=survey_slug,
            name_anchor_id=anchor.id,
        )
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
    ) -> TelnyxMessageResult:
        if tpl is not None:
            return FeedbackWaSendService.send_template(
                db,
                to_number=to_number,
                org_id=org_id,
                tpl=tpl,
                location=location,
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
