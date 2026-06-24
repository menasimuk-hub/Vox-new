"""Tests for Telnyx Zoom interview integration."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_zoom_service import InterviewZoomService, is_zoom_interview_order
from app.services.zoom_service import ZoomService


def _seed_zoom_order(db):
    org = Organisation(name="Zoom Org")
    db.add(org)
    db.flush()
    user = User(email=f"zoom-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    order = ServiceOrder(
        org_id=org.id,
        user_id=user.id,
        service_code="interview",
        title="Engineer",
        status="running",
        payment_status="approved",
        config_json='{"delivery":"zoom","role":"Engineer"}',
    )
    db.add(order)
    db.flush()
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Alex",
        email="alex@example.com",
        status="scheduled",
        result_json=json.dumps({"channel": "zoom", "zoom_meeting_id": "zm-123"}),
    )
    db.add(recipient)
    db.commit()
    return order, recipient


def test_is_zoom_interview_order():
    order = ServiceOrder(service_code="interview", config_json='{"delivery":"zoom"}')
    assert is_zoom_interview_order(order) is True
    order.config_json = '{"delivery":"ai_call"}'
    assert is_zoom_interview_order(order) is False


@patch("app.services.interview_zoom_service._telnyx_request")
@patch("app.services.interview_zoom_service.require_telnyx_api_key")
@patch("app.services.provider_settings.ProviderSettingsService.get_platform_config_decrypted")
def test_create_zoom_meeting_uses_telnyx_key(mock_cfg, mock_key, mock_request, app_client):
    mock_cfg.return_value = ({"api_key": "KEY01234567890123456789012345678901234567890123456789012"}, True)
    mock_key.return_value = ("KEY01234567890123456789012345678901234567890123456789012", "platform_integrations")
    mock_request.return_value = (
        201,
        {"data": {"id": "zm-999", "join_url": "https://zoom.us/j/999", "topic": "Test"}},
        "",
    )

    with get_sessionmaker()() as db:
        result = InterviewZoomService.create_zoom_meeting_via_telnyx(db, topic="Test")
        assert result["id"] == "zm-999"
        assert result["join_url"].startswith("https://zoom.us/")
        assert result["meeting_provider"] == "telnyx_zoom"
        mock_request.assert_called_once()
        args = mock_request.call_args
        assert args[0][1] == "POST"
        assert args[0][2] == "/zoom/meetings"


@patch("app.services.zoom_service.ZoomService.create_meeting")
@patch("app.services.zoom_service.ZoomService.is_configured")
@patch("app.services.interview_zoom_service._telnyx_request")
@patch("app.services.provider_settings.ProviderSettingsService.get_platform_config_decrypted")
def test_create_zoom_meeting_falls_back_to_zoom_oauth_on_telnyx_404(
    mock_cfg, mock_request, mock_zoom_configured, mock_create_meeting, app_client
):
    mock_cfg.return_value = ({"api_key": "KEY01234567890123456789012345678901234567890123456789012"}, True)
    mock_request.return_value = (404, {}, "The requested resource or URL could not be found.")
    mock_zoom_configured.return_value = True
    mock_create_meeting.return_value = {
        "id": "123456789",
        "join_url": "https://zoom.us/j/123456789",
        "start_url": "https://zoom.us/s/123456789",
    }

    with get_sessionmaker()() as db:
        result = InterviewZoomService.create_zoom_meeting_via_telnyx(db, topic="Fallback Test")
        assert result["id"] == "123456789"
        assert result["meeting_provider"] == "zoom_oauth"
        assert "telnyx_zoom_note" in result
        mock_create_meeting.assert_called_once()


@patch("app.services.interview_analysis_service.run_interview_analysis_if_needed")
@patch("app.services.interview_analysis_service.refresh_order_interview_report")
@patch("app.services.interview_zoom_service.InterviewZoomService.fetch_meeting_artifacts")
def test_finalize_recipient_artifacts(mock_fetch, mock_refresh, mock_analysis):
    mock_fetch.return_value = {
        "ready": True,
        "transcript": "Candidate answered all screening questions clearly.",
        "recording_url": "https://recordings.example/test.mp4",
    }

    with get_sessionmaker()() as db:
        order, recipient = _seed_zoom_order(db)
        ok = InterviewZoomService.finalize_recipient_artifacts(
            db,
            order=order,
            recipient=recipient,
            artifacts=mock_fetch.return_value,
            source="test",
        )
        db.refresh(recipient)
        db.refresh(order)
        assert ok is True
        assert recipient.status == "completed"
        parsed = json.loads(recipient.result_json or "{}")
        assert "Candidate answered" in parsed.get("transcript", "")
        assert parsed.get("recording_url") == "https://recordings.example/test.mp4"
        assert order.status == "completed"


def test_handle_webhook_ignores_unknown_events(app_client):
    with get_sessionmaker()() as db:
        out = InterviewZoomService.handle_webhook(db, {"data": {"event_type": "ping", "payload": {}}})
        assert out.get("ignored") is True


@patch("app.services.provider_settings.ProviderSettingsService.get_platform_config_decrypted")
def test_zoom_service_reads_telnyx_fallback_credentials(mock_cfg, app_client):  # noqa: ARG001
    def _fake(db, *, provider: str):
        if provider == "zoom":
            return ({}, False)
        if provider == "telnyx":
            return (
                {
                    "zoom_account_id": "acct_from_telnyx",
                    "zoom_client_id": "cid_from_telnyx",
                    "zoom_client_secret": "csec_from_telnyx",
                    "zoom_base_url": "https://api.zoom.us/v2",
                },
                True,
            )
        return ({}, False)

    mock_cfg.side_effect = _fake
    with get_sessionmaker()() as db:
        cfg = ZoomService._config(db)
    assert cfg["account_id"] == "acct_from_telnyx"
    assert cfg["client_id"] == "cid_from_telnyx"
    assert cfg["client_secret"] == "csec_from_telnyx"
    assert cfg["base_url"] == "https://api.zoom.us/v2"
