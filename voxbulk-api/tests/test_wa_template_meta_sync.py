"""Meta/Telnyx WhatsApp template sync helpers."""

from __future__ import annotations

import uuid

import pytest

from app.core.database import get_sessionmaker
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateError, SurveyWhatsappTemplateService
from app.services.wa_template_meta_sync import (
    META_ERROR_LANGUAGE_DELETION_LOCK,
    META_ERROR_LANGUAGE_UNSUPPORTED,
    META_ERROR_CONTENT_ALREADY_EXISTS,
    META_SUBCODE_CONTENT_ALREADY_EXISTS,
    admin_guidance_for_meta_error,
    enrich_template_push_error_payload,
    http_status_for_template_sync_error,
    normalize_wa_template_language,
    parse_meta_error_from_provider_detail,
    suggest_alternate_template_name,
    validate_wa_template_name,
)


def test_normalize_wa_template_language_accepts_codes():
    code, err = normalize_wa_template_language("en_GB")
    assert err is None
    assert code == "en_GB"


def test_normalize_wa_template_language_maps_display_text():
    code, err = normalize_wa_template_language("English (US)")
    assert err is None
    assert code == "en_US"


def test_normalize_wa_template_language_rejects_invalid():
    code, err = normalize_wa_template_language("English US only")
    assert code is None
    assert err is not None


def test_parse_meta_deletion_lock_error():
    detail = (
        'meta api error: {"error":{"message":"Invalid parameter","error_subcode":2388023,'
        '"error_user_title":"Message template language is being deleted",'
        '"error_user_msg":"New English (US) content can\'t be added"}}'
    )
    parsed = parse_meta_error_from_provider_detail(detail)
    assert parsed["kind"] == META_ERROR_LANGUAGE_DELETION_LOCK
    assert parsed["subcode"] == 2388023


def test_parse_meta_language_unsupported_error():
    detail = (
        'meta api error: {"error":{"message":"Invalid parameter","error_subcode":2388049,'
        '"error_user_title":"Message template language is not supported",'
        '"error_user_msg":"Content can\'t be added for this language"}}'
    )
    parsed = parse_meta_error_from_provider_detail(detail)
    assert parsed["kind"] == META_ERROR_LANGUAGE_UNSUPPORTED
    assert parsed["subcode"] == 2388049


def test_enrich_push_error_payload_suggests_rename():
    payload = enrich_template_push_error_payload(
        message="Push failed",
        template_name="interview_email_sent",
        language="en_US",
        provider_error='meta api error: {"error":{"error_subcode":2388023}}',
        status_code=503,
    )
    assert payload["meta_error_kind"] == META_ERROR_LANGUAGE_DELETION_LOCK
    assert payload["requires_rename"] is True
    assert payload["suggested_template_name"] == "interview_email_sent_v2"
    assert payload["blocking"] is True
    assert http_status_for_template_sync_error(payload) == 422


def test_enrich_push_error_payload_language_fix():
    payload = enrich_template_push_error_payload(
        message="Push failed",
        template_name="voxbulk_survey_foo_standard",
        language="English (US)",
        provider_error='meta api error: {"error":{"error_subcode":2388049}}',
        status_code=503,
    )
    assert payload["requires_language_fix"] is True
    assert payload["suggested_language"] == "en_GB"
    assert "en_GB" in admin_guidance_for_meta_error(
        kind=META_ERROR_LANGUAGE_UNSUPPORTED,
        template_name="voxbulk_survey_foo_standard",
        language="English (US)",
    )


def test_validate_wa_template_name():
    ok, err = validate_wa_template_name("interview_confirm_book")
    assert ok == "interview_confirm_book"
    assert err is None
    bad, err = validate_wa_template_name("Bad Name!")
    assert bad is None
    assert err is not None


def test_suggest_alternate_template_name():
    assert suggest_alternate_template_name("interview_email_sent", reason=META_ERROR_LANGUAGE_DELETION_LOCK) == "interview_email_sent_v2"


@pytest.fixture
def db():
    Session = get_sessionmaker()
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_rename_for_meta_sync_resets_remote_link(db):
    row = TelnyxWhatsappTemplate(
        telnyx_record_id="remote-123",
        template_id="999",
        name="interview_email_sent",
        language="en_US",
        status="APPROVED",
        local_sync_status="error",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    updated = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, "voxbulk_interview_email_sent")
    assert updated.name == "voxbulk_interview_email_sent"
    assert updated.telnyx_record_id.startswith("local-")
    assert updated.status == "LOCAL_DRAFT"


def test_push_blocks_invalid_language_before_provider(db, monkeypatch):
    local_id = f"local-{uuid.uuid4().hex}"
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=local_id,
        template_id=local_id,
        name="voxbulk_survey_test_standard",
        language="English US only",
        status="LOCAL_DRAFT",
        category="UTILITY",
        draft_components_json='[{"type":"BODY","text":"Hello","example":{"body_text":[["Alex"]]}}]',
        local_sync_status="draft",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    called = {"post": False}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            called["post"] = True
            raise AssertionError("provider should not be called")

    monkeypatch.setattr("app.services.survey_whatsapp_template_service.httpx.Client", lambda *a, **k: FakeClient())
    monkeypatch.setattr(
        "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
        lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
    )

    with pytest.raises(SurveyWhatsappTemplateError) as exc:
        SurveyWhatsappTemplateService.push_to_telnyx(db, row)
    assert called["post"] is False
    assert exc.value.payload.get("requires_language_fix") or exc.value.payload.get("language")


def test_parse_meta_content_already_exists_error():
    detail = (
        'meta api error: {"error":{"message":"Invalid parameter","error_subcode":2388024,'
        '"error_user_title":"Content in This Language Already Exists"}}'
    )
    parsed = parse_meta_error_from_provider_detail(detail)
    assert parsed["kind"] == META_ERROR_CONTENT_ALREADY_EXISTS
    assert parsed["subcode"] == META_SUBCODE_CONTENT_ALREADY_EXISTS


def test_push_links_existing_remote_template_instead_of_create(monkeypatch):
    from app.core.database import get_sessionmaker
    from app.services.interview_whatsapp_template_service import InterviewWhatsappTemplateService

    remote = [
        {
            "id": "019job-closed-remote",
            "template_id": "777",
            "name": "voxbulk_interview_job_closed",
            "language": "en_US",
            "category": "UTILITY",
            "status": "APPROVED",
            "components": [
                {
                    "type": "BODY",
                    "text": "Hi {{1}}, the {{2}} role at {{3}} has closed.",
                    "example": {"body_text": [["James", "accountant", "menasim"]]},
                }
            ],
        }
    ]

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            raise AssertionError("create should not run when remote template already exists")

    monkeypatch.setattr("app.services.survey_whatsapp_template_service.httpx.Client", lambda *a, **k: FakeClient())
    monkeypatch.setattr(
        "app.services.telnyx_whatsapp_template_sync_service.TelnyxWhatsappTemplateSyncService.fetch_from_telnyx",
        lambda db: remote,
    )
    monkeypatch.setattr(
        "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
        lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
    )

    with get_sessionmaker()() as db:
        InterviewWhatsappTemplateService.ensure_catalog_seeded(db)
        listed = InterviewWhatsappTemplateService.list_templates(db)
        row_data = next(item for item in listed if item["sales_template_key"] == "interview_job_closed")
        row = db.get(TelnyxWhatsappTemplate, row_data["id"])
        assert row is not None
        assert str(row.telnyx_record_id).startswith("local-")

        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        assert result["ok"] is True
        assert result["linked_existing_remote"] is True
        assert result["telnyx_request_mode"] == "link_existing_remote_template"
        assert row.telnyx_record_id == "019job-closed-remote"
        assert row.status == "APPROVED"
        assert "Linked to existing Telnyx template" in result["message"]
