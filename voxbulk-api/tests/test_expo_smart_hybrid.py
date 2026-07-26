"""Expo hybrid intents, templates, and package category limits."""

from __future__ import annotations

from app.services.expo.intent_router import apply_lead_field, detect_intent, prompt_for_correction
from app.services.expo.question_bank import (
    OPEN_FEEDBACK_KEY,
    SYSTEM_TEMPLATE_KEYS,
    build_vcard,
    default_question_config,
    with_topic_emoji,
)


def test_detect_change_email_inline():
    intent = detect_intent("please change my email to new@example.com")
    assert intent is not None
    assert intent["intent"] == "change_email"
    assert intent["value"] == "new@example.com"


def test_detect_list_and_send_all():
    assert detect_intent("can you list your products?")["intent"] == "list_products"
    assert detect_intent("send me all the catalogues")["intent"] == "send_all"


def test_detect_skip():
    assert detect_intent("skip")["intent"] == "skip"
    assert detect_intent("List Products Ltd") is None


def test_apply_lead_field_email():
    class Lead:
        visitor_email = None
        visitor_phone = None
        name = None
        company = None

    lead = Lead()
    msg = apply_lead_field(lead, "email", "a@b.com")
    assert lead.visitor_email == "a@b.com"
    assert "a@b.com" in msg
    assert prompt_for_correction("email").startswith("📧")


def test_default_question_config_includes_open_feedback():
    cfg = default_question_config()
    keys = [s["key"] for s in cfg["steps"]]
    assert OPEN_FEEDBACK_KEY in keys
    assert keys[-1] == OPEN_FEEDBACK_KEY or OPEN_FEEDBACK_KEY in keys


def test_system_template_keys_cover_closing():
    for key in ("thank_you", "company_card", "post_complete_handoff", "open_feedback", "contact"):
        assert key in SYSTEM_TEMPLATE_KEYS


def test_build_vcard_contains_rep():
    vcf = build_vcard(
        company_name="Acme",
        website="https://acme.example",
        reps=[{"name": "Sam Lee", "email": "sam@acme.example", "mobile": "+447700900123"}],
    )
    assert "BEGIN:VCARD" in vcf
    assert "Sam Lee" in vcf
    assert "sam@acme.example" in vcf


def test_with_topic_emoji_open_feedback():
    assert with_topic_emoji("open_feedback", "Anything else?").startswith("📝")
