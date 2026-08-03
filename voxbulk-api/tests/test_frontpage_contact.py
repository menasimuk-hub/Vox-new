"""Frontpage contact form — ticket + optional email."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.frontpage_contact_service import FrontpageContactError, send_frontpage_contact


def test_frontpage_contact_rejects_short_message(monkeypatch):
    monkeypatch.setattr(
        "app.services.frontpage_contact_service.SmtpMailerService.send_html",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not send")),
    )
    try:
        send_frontpage_contact(
            SimpleNamespace(),
            name="Jane",
            email="jane@example.com",
            message="Hi",
        )
        assert False, "expected FrontpageContactError"
    except FrontpageContactError as exc:
        assert "10 characters" in str(exc)


def test_frontpage_contact_honeypot_skips_send(monkeypatch):
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("SMTP should not run for honeypot")

    monkeypatch.setattr(
        "app.services.frontpage_contact_service.SmtpMailerService.send_html",
        boom,
    )
    monkeypatch.setattr(
        "app.services.frontpage_contact_service.SmtpMailerService.send_plain",
        boom,
    )
    monkeypatch.setattr(
        "app.services.frontpage_contact_service._create_contact_ticket",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ticket should not run for honeypot")),
    )
    result = send_frontpage_contact(
        SimpleNamespace(),
        name="Jane Smith",
        email="jane@example.com",
        message="I would like a demo of VoxBulk please.",
        website="http://spam.example",
    )
    assert called["n"] == 0
    assert result.get("skipped") is True


def test_frontpage_contact_creates_ticket_then_emails(monkeypatch):
    sends = {"html": 0}

    monkeypatch.setattr(
        "app.services.frontpage_contact_service._create_contact_ticket",
        lambda *_a, **_k: "TKT-000042",
    )

    def fake_html(*_a, **_k):
        sends["html"] += 1

    monkeypatch.setattr(
        "app.services.frontpage_contact_service.SmtpMailerService.send_html",
        fake_html,
    )
    result = send_frontpage_contact(
        MagicMock(),
        name="Jane Smith",
        email="jane@example.com",
        message="I would like a demo of VoxBulk please.",
    )
    assert result["ok"] is True
    assert result["ticket_ref"] == "TKT-000042"
    assert sends["html"] == 1
