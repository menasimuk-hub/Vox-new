"""Tests for WA template cleanup protection rules."""

from __future__ import annotations

import uuid

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.wa_template_cleanup_sync_service import is_protected_template, is_survey_product_row


def _row(*, name: str, sales_template_key: str | None = None) -> TelnyxWhatsappTemplate:
    return TelnyxWhatsappTemplate(
        id=1,
        telnyx_record_id=f"local-{uuid.uuid4().hex}",
        template_id=f"local-{uuid.uuid4().hex}",
        name=name,
        sales_template_key=sales_template_key,
        language="en_GB",
        status="LOCAL_DRAFT",
    )


def test_survey_interview_step_name_is_not_protected():
    row = _row(name="voxbulk_survey_interview_process_rating_abc_3107e6")
    assert is_protected_template(row) is False
    assert is_survey_product_row(row) is True


def test_ai_interview_template_is_protected():
    row = _row(name="voxbulk_interview_book")
    assert is_protected_template(row) is True
    assert is_survey_product_row(row) is False


def test_sales_template_is_protected():
    row = _row(name="voxbulk_sales_offer", sales_template_key="sales_offer")
    assert is_protected_template(row) is True


def test_format_template_push_error_includes_subcode():
    from app.services.wa_template_meta_sync import format_template_push_error
    from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateError

    exc = SurveyWhatsappTemplateError(
        "Meta Graph API error (100): Invalid parameter",
        payload={
            "admin_guidance": "Meta rejected template body example.",
            "meta_error_subcode": 2388043,
        },
    )
    msg = format_template_push_error(exc)
    assert "2388043" in msg
    assert "body example" in msg.lower()
