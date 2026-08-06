"""Expo UX polish — voice accept, choice options, rep emails, purpose icons."""

from __future__ import annotations

from app.services.expo.expo_email_service import ExpoEmailService
from app.services.expo.question_bank import WEB_CHOICE_OPTIONS, WEB_VOICE_KEYS, web_ui_for_question_key
from app.services.expo.session_flow_service import _consent_asset_option_label
from app.services.voice_transcription_service import looks_like_hallucination


def test_web_voice_keys_only_open_fields():
    assert WEB_VOICE_KEYS == frozenset({"interest", "open_feedback"})
    assert web_ui_for_question_key("budget")["input"] == "choice"
    assert web_ui_for_question_key("volume")["input"] == "choice"
    assert web_ui_for_question_key("offer_interest")["input"] == "choice"
    assert web_ui_for_question_key("interest")["allow_voice"] is True
    assert web_ui_for_question_key("timeline")["allow_voice"] is False


def test_budget_and_volume_have_numbered_options():
    assert len(WEB_CHOICE_OPTIONS["budget"]) >= 4
    assert len(WEB_CHOICE_OPTIONS["volume"]) >= 4


def test_purpose_icon_on_consent_label():
    label = _consent_asset_option_label(
        {
            "purpose": "catalogue",
            "title": "300W Solar Panel",
            "product_name": "300W Solar Panel",
        }
    )
    assert label.startswith("📘")
    assert "Catalogue" in label or "Solar" in label


def test_exhibitor_emails_include_representatives():
    class _Booth:
        created_by_user_id = None
        org_id = "org-1"
        visitor_contact_email = "stand@example.com"
        representative_contacts_json = (
            '[{"name":"Sam","email":"sam.rep@example.com","mobile":"+447700900001"}]'
        )

    class _Db:
        def get(self, *_a, **_k):
            return None

        def execute(self, *_a, **_k):
            class _R:
                def scalars(self):
                    return self

                def all(self):
                    return []

            return _R()

    emails = ExpoEmailService._exhibitor_emails(_Db(), booth=_Booth())  # type: ignore[arg-type]
    assert "sam.rep@example.com" in emails
    assert "stand@example.com" in emails


def test_usable_voice_not_blocked_by_hallucination_helper():
    assert looks_like_hallucination("We need solar panels for a farm project") is False
