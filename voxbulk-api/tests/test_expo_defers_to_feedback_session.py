"""Expo post-complete handoff must not steal active Customer Feedback replies."""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackSession
from app.models.organisation import Organisation
from app.services.expo.whatsapp_service import ExpoWhatsappService


@pytest.fixture()
def db():
    with get_sessionmaker()() as session:
        yield session


def _ensure_org(db, org_id: str) -> None:
    if db.get(Organisation, org_id) is None:
        db.add(Organisation(id=org_id, name="Expo CF defer test"))
        db.commit()


def test_expo_defers_when_feedback_session_active(db):
    org_id = str(uuid.uuid4())
    _ensure_org(db, org_id)
    phone = "+447700900111"
    now = datetime.utcnow()
    db.add(
        FeedbackSession(
            id=str(uuid.uuid4()),
            org_id=org_id,
            location_id=str(uuid.uuid4()),
            visitor_phone=phone,
            entry_channel="whatsapp",
            status="active",
            current_step=0,
            started_at=now,
            created_at=now,
        )
    )
    db.commit()

    completed = MagicMock()
    completed.id = str(uuid.uuid4())
    completed.org_id = org_id

    with (
        patch(
            "app.services.expo.session_flow_service.ExpoSessionFlowService.find_active_session",
            return_value=None,
        ),
        patch(
            "app.services.expo.session_flow_service.ExpoSessionFlowService.find_recent_completed_session",
            return_value=completed,
        ),
        patch(
            "app.services.expo.booth_service.find_expo_token_in_text",
            return_value=None,
        ),
        patch.object(ExpoWhatsappService, "_send", return_value=True) as send_mock,
    ):
        result = ExpoWhatsappService.try_handle_inbound(
            db,
            from_phone=phone,
            body="Poor",
            org_id=org_id,
        )

    assert result.get("handled") is False
    assert result.get("reason") == "deferred_to_other_product_session"
    send_mock.assert_not_called()


def test_expo_post_complete_still_runs_without_feedback(db):
    org_id = str(uuid.uuid4())
    phone = "+447700900222"
    completed = MagicMock()
    completed.id = str(uuid.uuid4())
    completed.org_id = org_id

    with (
        patch(
            "app.services.expo.session_flow_service.ExpoSessionFlowService.find_active_session",
            return_value=None,
        ),
        patch(
            "app.services.expo.session_flow_service.ExpoSessionFlowService.find_recent_completed_session",
            return_value=completed,
        ),
        patch(
            "app.services.expo.session_flow_service.ExpoSessionFlowService._lead_for_session",
            return_value=None,
        ),
        patch(
            "app.services.expo.session_flow_service.ExpoSessionFlowService.record_post_complete_question",
        ),
        patch(
            "app.services.expo.booth_service.find_expo_token_in_text",
            return_value=None,
        ),
        patch(
            "app.services.customer_feedback.whatsapp_service.FeedbackWhatsappService._active_session",
            return_value=None,
        ),
        patch(
            "app.services.smart_card.whatsapp_service.SmartCardWhatsappService.find_active_session",
            return_value=None,
        ),
        patch.object(ExpoWhatsappService, "_send", return_value=True) as send_mock,
    ):
        result = ExpoWhatsappService.try_handle_inbound(
            db,
            from_phone=phone,
            body="Poor",
            org_id=org_id,
        )

    assert result.get("handled") is True
    assert result.get("reason") == "post_complete_handoff"
    send_mock.assert_called_once()
