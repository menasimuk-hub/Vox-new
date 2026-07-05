"""Tests for anonymous vs named welcome template resolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.survey_system_template_service import (
    WELCOME_TEMPLATE_ANONYMOUS_NAME,
    WELCOME_TEMPLATE_NAMED_NAME,
    SurveySystemTemplateService,
)


def test_resolve_welcome_template_named():
    db = MagicMock()
    row = MagicMock()
    row.id = 42
    row.status = "APPROVED"
    row.name = WELCOME_TEMPLATE_NAMED_NAME
    row.telnyx_record_id = "550e8400-e29b-41d4-a716-446655440000"
    row.parent_template_id = None
    db.execute.return_value.scalar_one_or_none.return_value = row

    with patch(
        "app.services.survey_whatsapp_template_service.resolve_sendable_template_row",
        return_value=row,
    ):
        resolved = SurveySystemTemplateService.resolve_welcome_template_for_survey(
            db, {"anonymous_responses": False}
        )
    assert resolved is row


def test_resolve_welcome_template_anonymous():
    db = MagicMock()
    row = MagicMock()
    row.id = 99
    row.status = "APPROVED"
    row.name = WELCOME_TEMPLATE_ANONYMOUS_NAME
    row.telnyx_record_id = "550e8400-e29b-41d4-a716-446655440001"
    row.parent_template_id = None
    db.execute.return_value.scalar_one_or_none.return_value = row

    with patch(
        "app.services.survey_whatsapp_template_service.resolve_sendable_template_row",
        return_value=row,
    ):
        resolved = SurveySystemTemplateService.resolve_welcome_template_for_survey(
            db, {"anonymous_responses": True}
        )
    assert resolved is row


def test_resolve_welcome_template_id_returns_none_when_missing():
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None

    with patch("app.services.survey_system_template_service.logger") as log_mock:
        tpl_id = SurveySystemTemplateService.resolve_welcome_template_id_for_survey(db, {"anonymous_responses": True})
    assert tpl_id is None
    log_mock.error.assert_called()
