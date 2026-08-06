"""Expo / Smart Card WhatsApp: catalogue as file + Skip on open questions."""

from __future__ import annotations

from app.services.expo.question_bank import _DEFAULT_SELECTED_KEYS
from app.services.expo.session_flow_service import WA_OPEN_SKIP_HINT, _format_whatsapp_step_prompt
from app.services.expo.whatsapp_service import (
    _asset_supports_document_send,
    _wa_document_url,
)
from app.services.smart_card.asset_delivery_service import supports_document_send
from app.services.smart_card.session_flow_service import DEFAULT_STEPS, WA_SKIP_HINT


def test_default_question_sets_include_more_choices():
    assert "decision_maker" in _DEFAULT_SELECTED_KEYS
    assert "budget" in _DEFAULT_SELECTED_KEYS
    assert "volume" in _DEFAULT_SELECTED_KEYS
    assert "decision_maker" in DEFAULT_STEPS
    assert "budget" in DEFAULT_STEPS
    assert "volume" in DEFAULT_STEPS


def test_wa_open_prompt_offers_skip():
    prompt = _format_whatsapp_step_prompt("interest", "What are you looking for?")
    assert WA_OPEN_SKIP_HINT in prompt
    assert "What are you looking for?" in prompt


def test_wa_choice_prompt_is_numbered_not_ask_only():
    prompt = _format_whatsapp_step_prompt("timeline", "When?")
    assert "1️⃣" in prompt or "1" in prompt
    assert "Reply with the number" in prompt
    assert WA_OPEN_SKIP_HINT not in prompt


def test_stored_file_prefers_document_send():
    asset = {"storage_path": "data/expo/demo/spec.pdf", "kind": "other", "title": "Spec"}
    assert _asset_supports_document_send(asset) is True
    assert supports_document_send(asset) is True


def test_wa_document_url_strips_tracking_query():
    assert (
        _wa_document_url("https://api.voxbulk.com/public/expo/assets/tok/id?lead_id=abc")
        == "https://api.voxbulk.com/public/expo/assets/tok/id"
    )


def test_smart_card_skip_hint_constant():
    assert "Skip" in WA_SKIP_HINT
