"""Career / interview email must send when SMTP fails if Resend is configured."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.career_email_service import CareerEmailService


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


def test_send_falls_back_to_resend_when_smtp_fails(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(
        "app.services.career_email_service._resend_api_key",
        lambda _db: "re_test_key",
    )
    monkeypatch.setattr(
        "app.services.career_email_service.careers_from_address",
        lambda _db: ("VOXBULK Careers", "careers@voxbulk.com"),
    )
    monkeypatch.setattr(
        "app.services.career_email_service.SmtpMailerService.send_html",
        MagicMock(side_effect=__import__(
            "app.services.smtp_mailer_service", fromlist=["SmtpMailerError"]
        ).SmtpMailerError("SMTP is disabled")),
    )
    resend_send = MagicMock(return_value={"ok": True, "email_id": "em_1"})
    monkeypatch.setattr(
        "app.services.resend_service.ResendService.send_email",
        resend_send,
    )
    CareerEmailService.send(
        db,
        to_email="candidate@example.com",
        subject="Test",
        body="<p>Hello</p>",
    )
    resend_send.assert_called_once()
