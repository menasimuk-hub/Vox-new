"""Interview email uses the same SMTP deliver path as admin send-test."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.career_email_service import CareerEmailService


def test_send_templated_critical_delivers_via_shared_smtp_path(monkeypatch):
    db = MagicMock()
    deliver = MagicMock()
    monkeypatch.setattr(
        "app.services.career_email_service._render_interview_template",
        lambda *a, **k: ("Subject", "<p>Hi {{candidate_name}}</p>"),
    )
    monkeypatch.setattr("app.services.career_email_service._deliver_message", deliver)
    monkeypatch.setattr(
        "app.services.career_email_service.careers_reply_to",
        lambda _db: "careers@voxbulk.com",
    )
    ok, err = CareerEmailService.send_templated_critical(
        db,
        template_key="interview_booking_invite",
        to_email="candidate@example.com",
        variables={"candidate_name": "Alex", "booking_url": "https://example.com/book/x"},
    )
    assert ok is True
    assert err is None
    deliver.assert_called_once()
    assert deliver.call_args.kwargs["reply_to"] == "careers@voxbulk.com"


def test_interview_template_send_test_uses_critical_path(monkeypatch):
    db = MagicMock()
    critical = MagicMock(return_value=(True, None))
    monkeypatch.setattr(
        "app.services.career_email_service.CareerEmailService.send_templated_critical",
        critical,
    )
    ok, err = CareerEmailService.send_template_test(
        db,
        template_key="interview_booking_invite",
        to_email="test@example.com",
    )
    assert ok is True
    assert err is None
    critical.assert_called_once()
