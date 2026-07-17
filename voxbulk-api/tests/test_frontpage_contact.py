"""Frontpage contact form validation (no SMTP send)."""

from types import SimpleNamespace

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
    send_frontpage_contact(
        SimpleNamespace(),
        name="Jane Smith",
        email="jane@example.com",
        message="I would like a demo of VoxBulk please.",
        website="http://spam.example",
    )
    assert called["n"] == 0
