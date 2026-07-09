"""Tests for interview WhatsApp send helper."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.interview_whatsapp_send_service import InterviewWhatsappSendService
from app.services.telnyx_messaging_service import TelnyxMessageResult


class _FakeRow:
    name = "voxbulk_interview_email_sent"
    language = "en_US"
    id = 99


def test_interview_wa_retries_language_on_132001(monkeypatch):
    calls: list[dict] = []

    def fake_send(db, **kwargs):
        calls.append(kwargs)
        if kwargs.get("template_language") == "en_US":
            return TelnyxMessageResult(
                ok=False,
                status="http_error",
                detail="Meta Graph API error (132001): Template name does not exist in the translation",
                channel="whatsapp",
            )
        return TelnyxMessageResult(ok=True, status="queued", external_id="wamid.1", channel="whatsapp")

    monkeypatch.setattr(
        "app.services.interview_whatsapp_send_service.TelnyxMessagingService.send_whatsapp",
        fake_send,
    )
    monkeypatch.setattr(
        "app.services.interview_whatsapp_send_service.resolve_whatsapp_template_languages",
        lambda db: ["en_US", "en_GB"],
    )
    monkeypatch.setattr(
        "app.services.interview_whatsapp_send_service.WaTemplateProfilePushService.send_template_id_for_active_profile",
        lambda *a, **k: "tpl-123",
    )

    result = InterviewWhatsappSendService.send_template_or_plain(
        MagicMock(),
        to_number="+447954823445",
        body="Dear Alex, check your email.",
        org_id="org-1",
        template_row=_FakeRow(),
        template_components=[{"type": "BODY", "text": "Hi"}],
    )
    assert result.ok is True
    assert len(calls) == 2
    assert calls[0]["template_language"] == "en_US"
    assert calls[1]["template_language"] == "en_GB"


def test_interview_wa_plain_fallback_after_template_failure(monkeypatch):
    template_calls = 0
    plain_calls = 0

    def fake_send(db, **kwargs):
        nonlocal template_calls, plain_calls
        if kwargs.get("template_name") or kwargs.get("template_id"):
            template_calls += 1
            return TelnyxMessageResult(
                ok=False,
                status="http_error",
                detail="Meta Graph API error (132001): Template name does not exist in the translation",
                channel="whatsapp",
            )
        plain_calls += 1
        return TelnyxMessageResult(ok=True, status="queued", external_id="wamid.plain", channel="whatsapp")

    monkeypatch.setattr(
        "app.services.interview_whatsapp_send_service.TelnyxMessagingService.send_whatsapp",
        fake_send,
    )
    monkeypatch.setattr(
        "app.services.interview_whatsapp_send_service.resolve_whatsapp_template_languages",
        lambda db: ["en_US"],
    )
    monkeypatch.setattr(
        "app.services.interview_whatsapp_send_service.WaTemplateProfilePushService.send_template_id_for_active_profile",
        lambda *a, **k: "tpl-123",
    )

    result = InterviewWhatsappSendService.send_template_or_plain(
        MagicMock(),
        to_number="+447954823445",
        body="Dear Alex, check your email.",
        org_id="org-1",
        template_row=_FakeRow(),
    )
    assert result.ok is True
    assert template_calls >= 1
    assert plain_calls == 1
