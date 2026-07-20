"""Regression: welcome send must persist recipient.status=sent across result save."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_save_recipient_result_preserves_dirty_status(db, monkeypatch):
    from app.models.service_order import ServiceOrderRecipient
    from app.services import survey_whatsapp_conversation_service as svc

    recipient = ServiceOrderRecipient(
        id="rec-1",
        order_id="ord-1",
        row_number=1,
        name="Test",
        phone="+447700900000",
        status="pending",
        result_json="{}",
    )
    db.add(recipient)
    db.commit()

    recipient.status = "sent"
    monkeypatch.setattr(svc, "recipient_result_lock", lambda _rid: MagicMock(__enter__=lambda s: s, __exit__=lambda *a: False))
    # Use real lock path — patch translation only
    from contextlib import nullcontext

    monkeypatch.setattr(
        "app.services.survey_recipient_result_lock.recipient_result_lock",
        lambda _rid: nullcontext(),
    )
    monkeypatch.setattr(
        "app.services.survey_wa_translation_service.SurveyWaTranslationService.merge_preserved_translations",
        lambda existing, payload: payload,
    )
    monkeypatch.setattr(
        "app.services.survey_wa_translation_service.SurveyWaTranslationService.reconcile_missing_translations",
        lambda *a, **k: None,
    )

    svc._save_recipient_result(db, recipient, {"channel": "whatsapp", "wa_conversation": {"step": 0}})
    db.refresh(recipient)
    assert recipient.status == "sent"


def test_save_recipient_result_explicit_status(db, monkeypatch):
    from contextlib import nullcontext

    from app.models.service_order import ServiceOrderRecipient
    from app.services import survey_whatsapp_conversation_service as svc

    recipient = ServiceOrderRecipient(
        id="rec-2",
        order_id="ord-2",
        row_number=1,
        name="Test",
        phone="+447700900001",
        status="pending",
        result_json='{"error":"outside_wa_survey_hours"}',
    )
    db.add(recipient)
    db.commit()

    monkeypatch.setattr(
        "app.services.survey_recipient_result_lock.recipient_result_lock",
        lambda _rid: nullcontext(),
    )
    monkeypatch.setattr(
        "app.services.survey_wa_translation_service.SurveyWaTranslationService.merge_preserved_translations",
        lambda existing, payload: {**existing, **payload},
    )
    monkeypatch.setattr(
        "app.services.survey_wa_translation_service.SurveyWaTranslationService.reconcile_missing_translations",
        lambda *a, **k: None,
    )

    svc._save_recipient_result(
        db,
        recipient,
        {"channel": "whatsapp", "wa_conversation": {"intro_sent_at": "x", "step": 0}},
        status="sent",
    )
    db.refresh(recipient)
    assert recipient.status == "sent"


def test_match_recipient_allows_pending_with_intro():
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.survey_whatsapp_conversation_service import _match_recipient_conversation

    order = ServiceOrder(
        id="o1",
        org_id="org",
        user_id="u",
        service_code="survey",
        title="t",
        status="running",
    )
    recipient = ServiceOrderRecipient(
        id="r1",
        order_id="o1",
        row_number=1,
        name="Leen",
        phone="+971506166042",
        status="pending",
        result_json='{"wa_conversation":{"step":0,"intro_sent_at":"2026-07-20T07:57:44","awaiting_start":true}}',
    )
    assert _match_recipient_conversation(order, recipient) is True
    assert _match_recipient_conversation(order, recipient, session_step=0) is True
