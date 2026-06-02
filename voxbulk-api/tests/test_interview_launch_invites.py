"""Unit tests for launch invite dispatch (no DB)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.interview_booking_service import InterviewBookingService


def test_recipients_pending_invite_email_when_missing(monkeypatch):
    order = MagicMock()
    recipient = MagicMock()
    recipient.email = "candidate@example.com"
    recipient.result_json = '{"invite_wa_sent_at":"2026-06-01T12:00:00"}'
    monkeypatch.setattr(
        "app.services.interview_booking_service.ServiceOrderService.get_recipients",
        lambda _db, _oid: [recipient],
    )
    assert InterviewBookingService.recipients_pending_invite_email(MagicMock(), order) is True


def test_recipients_pending_invite_email_false_when_sent(monkeypatch):
    order = MagicMock()
    recipient = MagicMock()
    recipient.email = "candidate@example.com"
    recipient.result_json = '{"invite_email_sent_at":"2026-06-01T12:00:00"}'
    monkeypatch.setattr(
        "app.services.interview_booking_service.ServiceOrderService.get_recipients",
        lambda _db, _oid: [recipient],
    )
    assert InterviewBookingService.recipients_pending_invite_email(MagicMock(), order) is False
