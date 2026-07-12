"""Tests for WA Survey AI follow-up scheduling helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.customer_feedback.feedback_ai_followup_service import resolve_followup_delay_hours
from app.services.survey_ai_followup_service import (
    _callable_phone,
    _has_written_reason,
    handle_survey_ai_followup_telnyx_event,
)


def test_resolve_followup_delay_hours_default_24():
    assert resolve_followup_delay_hours({"enabled": True}) == 24
    assert resolve_followup_delay_hours({"delay_hours": 48}) == 48


def test_resolve_followup_delay_hours_force_immediate_env():
    with patch("app.core.config.get_settings") as settings:
        settings.return_value = MagicMock(ai_followup_force_immediate=True)
        assert resolve_followup_delay_hours({"delay_hours": 24}) == 0


def test_resolve_followup_delay_hours_config_override():
    with patch("app.core.config.get_settings") as settings:
        settings.return_value = MagicMock(ai_followup_force_immediate=False)
        assert resolve_followup_delay_hours({"delay_hours": 24, "force_immediate": True}) == 0
        assert resolve_followup_delay_hours({"delay_hours": 0}) == 0


def test_callable_phone_rejects_web():
    assert _callable_phone("+447954823445") is True
    assert _callable_phone("web:abc") is False


def test_has_written_reason_detects_tell_us_more():
    recipient = MagicMock()
    recipient.result_json = (
        '{"wa_conversation":{"answers":[{"step_role":"tell_us_more","answer_text":"Waiting too long today"}]}}'
    )
    assert _has_written_reason(recipient) is True


def test_has_written_reason_ignores_short_skip():
    recipient = MagicMock()
    recipient.result_json = '{"wa_conversation":{"answers":[{"step_role":"tell_us_more","answer_text":"skip"}]}}'
    assert _has_written_reason(recipient) is False


def test_handle_survey_ai_followup_ignores_feedback_calls(db_session=None):
    # Lightweight: no DB needed when client_state is missing survey flag
    from sqlalchemy.orm import Session

    payload = {
        "data": {
            "event_type": "call.answered",
            "payload": {
                "call_control_id": "cc-1",
                "client_state": None,
            },
        }
    }
    # Use a mock session — handler returns False before DB when not survey followup
    mock_db = MagicMock(spec=Session)
    assert handle_survey_ai_followup_telnyx_event(mock_db, payload) is False
