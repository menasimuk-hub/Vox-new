"""Tests for interview candidate activity timeline."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.interview_activity_service import InterviewActivityService


def _recipient(**kwargs) -> ServiceOrderRecipient:
    row = ServiceOrderRecipient(
        id=kwargs.get("id", "rec-1"),
        order_id=kwargs.get("order_id", "ord-1"),
        row_number=1,
        name=kwargs.get("name", "Alex Candidate"),
        phone="+447700900123",
        email="alex@example.com",
        status=kwargs.get("status", "pending"),
        result_json=kwargs.get("result_json"),
    )
    row.created_at = datetime.utcnow()
    return row


def test_activity_status_awaiting_booking():
    r = _recipient(
        result_json=json.dumps({"invite_email_sent_at": "2026-05-01T10:00:00"}),
    )
    assert InterviewActivityService.activity_status(r) == "awaiting_booking"


def test_activity_status_report_ready():
    r = _recipient(
        status="completed",
        result_json=json.dumps({"analysis_saved_at": "2026-05-02T12:00:00", "analysis": {"score": 82}}),
    )
    assert InterviewActivityService.activity_status(r) == "report_ready"


def test_timeline_includes_invite_events():
    order = ServiceOrder(
        id="ord-1",
        org_id="org-1",
        user_id="user-1",
        service_code="interview",
        title="Engineer",
        status="running",
        payment_status="approved",
    )
    r = _recipient(
        result_json=json.dumps(
            {
                "invite_email_sent_at": "2026-05-01T10:00:00",
                "invite_wa_sent_at": "2026-05-01T10:01:00",
            }
        ),
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute.return_value = mock_result
    payload = InterviewActivityService.timeline(db, order, r)
    codes = [e["code"] for e in payload["events"]]
    assert "invite_email" in codes
    assert "invite_wa" in codes
    assert payload["activity_status"] == "awaiting_booking"


def test_activity_status_booked_waiting():
    future = (datetime.utcnow() + timedelta(days=2)).isoformat()
    r = _recipient(
        result_json=json.dumps({"booked_start_at": future, "booking_confirmed_at": "2026-05-01T11:00:00"}),
    )
    assert InterviewActivityService.activity_status(r) == "booked_waiting"
