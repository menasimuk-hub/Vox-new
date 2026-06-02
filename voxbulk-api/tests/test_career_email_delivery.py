"""Career / interview email uses admin SMTP From (same as template send-test)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.career_email_service import CareerEmailService, smtp_from_address


def test_send_templated_critical_uses_defaults_when_template_disabled(monkeypatch):
    db = MagicMock()
    send_plain = MagicMock()
    monkeypatch.setattr(
        "app.services.career_email_service.CareerEmailService.send_templated_optional",
        lambda *a, **k: (False, "template_disabled"),
    )
    monkeypatch.setattr(
        "app.services.career_email_service.CareerEmailService.send",
        send_plain,
    )
    ok, err = CareerEmailService.send_templated_critical(
        db,
        template_key="interview_booking_invite",
        to_email="candidate@example.com",
        variables={
            "candidate_name": "Alex",
            "role": "Engineer",
            "company_name": "Acme",
            "booking_url": "https://dashboard.voxbulk.com/book/tok",
        },
    )
    assert ok is True
    assert err is None
    send_plain.assert_called_once()


def test_send_uses_smtp_from_and_reply_to(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(
        "app.services.career_email_service.smtp_from_address",
        lambda _db: ("VoxBulk", "noreply@voxbulk.com"),
    )
    monkeypatch.setattr(
        "app.services.career_email_service.careers_reply_to",
        lambda _db: "careers@voxbulk.com",
    )
    send_html = MagicMock()
    monkeypatch.setattr(
        "app.services.career_email_service.SmtpMailerService.send_html",
        send_html,
    )
    CareerEmailService.send(
        db,
        to_email="candidate@example.com",
        subject="Test",
        body="<p>Hello</p>",
    )
    send_html.assert_called_once()
    kwargs = send_html.call_args.kwargs
    assert kwargs["from_email"] == "noreply@voxbulk.com"
    assert kwargs["reply_to"] == "careers@voxbulk.com"
