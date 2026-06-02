"""Interview emails must send From careers@ via SMTP."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.career_email_service import CareerEmailService, careers_from_address


def test_send_uses_careers_mailbox_as_from(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(
        "app.services.career_email_service.careers_from_address",
        lambda _db: ("VOXBULK Careers", "careers@voxbulk.com"),
    )
    send_html = MagicMock()
    monkeypatch.setattr(
        "app.services.career_email_service.SmtpMailerService.send_html",
        send_html,
    )
    monkeypatch.setattr(
        "app.services.career_email_service._render_interview_template",
        lambda *a, **k: ("Invite", "<p>Book</p>"),
    )
    CareerEmailService.send_templated_critical(
        db,
        template_key="interview_booking_invite",
        to_email="candidate@example.com",
        variables={"booking_url": "https://dashboard.voxbulk.com/book/tok"},
    )
    send_html.assert_called_once()
    assert send_html.call_args.kwargs["from_email"] == "careers@voxbulk.com"
    assert send_html.call_args.kwargs["from_name"] == "VOXBULK Careers"


def test_delivery_status_reports_careers_from(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(
        "app.services.career_email_service.careers_from_address",
        lambda _db: ("VOXBULK Careers", "careers@voxbulk.com"),
    )
    monkeypatch.setattr(
        "app.services.career_email_service.SmtpSettingsService.get_row",
        lambda _db: MagicMock(is_enabled=True, from_email="hello@voxbulk.com", from_name="VoxBulk"),
    )
    monkeypatch.setattr(
        "app.services.career_email_service.SmtpSettingsService.compute_status",
        lambda _row: (True, []),
    )
    from app.services.career_email_service import interview_email_delivery_status

    status = interview_email_delivery_status(db)
    assert status["interview_from_email"] == "careers@voxbulk.com"
    assert status["can_send_email"] is True
