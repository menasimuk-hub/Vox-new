"""WhatsApp template category validation and Telnyx sync UI labels."""

from __future__ import annotations

import json as json_module

import pytest

from app.core.database import get_sessionmaker
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_whatsapp_template_service import (
    LOCAL_STATUS_SAVED,
    TELNYX_SYNC_FAILED,
    TELNYX_SYNC_NOT_SYNCED,
    TELNYX_SYNC_OUT_OF_SYNC,
    TELNYX_SYNC_PENDING,
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    normalize_wa_template_category,
    survey_template_to_dict,
    telnyx_sync_action_message,
    telnyx_sync_ui_label,
    template_workflow_state,
)


def _seed_survey_type(db):
    SurveyTypeService.ensure_defaults(db)
    row = SurveyTypeService.get_by_slug(db, "customer_satisfaction")
    assert row is not None
    return row


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def test_normalize_category_requires_valid_values():
    assert normalize_wa_template_category("marketing") == "MARKETING"
    assert normalize_wa_template_category("UTILITY") == "UTILITY"
    with pytest.raises(SurveyWhatsappTemplateError):
        normalize_wa_template_category("PROMO")
    with pytest.raises(SurveyWhatsappTemplateError):
        normalize_wa_template_category("", required=True)


def test_push_blocks_without_category():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        row.category = None
        db.add(row)
        db.commit()
        with pytest.raises(SurveyWhatsappTemplateError, match="Template Category is required"):
            SurveyWhatsappTemplateService.push_to_telnyx(db, row)


def test_telnyx_sync_ui_labels():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        assert telnyx_sync_ui_label(row) == TELNYX_SYNC_NOT_SYNCED
        row.last_push_error = "Provider timeout"
        row.local_sync_status = "error"
        assert telnyx_sync_ui_label(row) == TELNYX_SYNC_FAILED
        row.telnyx_record_id = "telnyx-uuid"
        row.template_id = "telnyx-uuid"
        row.status = "PENDING"
        row.last_push_error = None
        row.local_sync_status = "in_sync"
        assert telnyx_sync_ui_label(row) == TELNYX_SYNC_PENDING
        assert telnyx_sync_action_message(row, ok=True) == TELNYX_SYNC_PENDING


def test_push_sends_category_and_refreshes(monkeypatch):
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type, category="UTILITY")
        captured = {"post": None, "get": 0}

        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, headers=None, json=None):
                captured["post"] = json
                components = json_module.loads(row.draft_components_json)
                return FakeResponse(
                    {
                        "data": {
                            "id": "telnyx-new-id",
                            "template_id": "999",
                            "status": "PENDING",
                            "category": "UTILITY",
                            "components": components,
                        }
                    }
                )

            def get(self, url, headers=None):
                captured["get"] += 1
                components = json_module.loads(row.draft_components_json)
                return FakeResponse(
                    {
                        "data": {
                            "id": "telnyx-new-id",
                            "template_id": "999",
                            "status": "PENDING",
                            "category": "UTILITY",
                            "components": components,
                        }
                    }
                )

        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.httpx.Client",
            lambda *a, **k: FakeClient(),
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
            lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_template_by_record_id",
            lambda db, record_id: {
                "id": "telnyx-new-id",
                "template_id": "999",
                "status": "PENDING",
                "category": "UTILITY",
                "components": json_module.loads(row.draft_components_json),
            },
        )
        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        assert captured["post"]["category"] == "UTILITY"
        assert result["sync_message"] == TELNYX_SYNC_PENDING
        assert result["category"] == "UTILITY"
        assert result["telnyx_template_id"] == "telnyx-new-id"


def test_save_draft_does_not_push(monkeypatch):
    pushed = {"count": 0}

    def _fail_push(*args, **kwargs):
        pushed["count"] += 1
        raise AssertionError("save_draft must not call Telnyx")

    monkeypatch.setattr(
        SurveyWhatsappTemplateService,
        "push_to_telnyx",
        staticmethod(_fail_push),
    )
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type, category="MARKETING")
        updated = SurveyWhatsappTemplateService.save_draft(
            db,
            row,
            {"display_name": "Updated name", "category": "UTILITY"},
        )
        assert pushed["count"] == 0
        tpl = survey_template_to_dict(updated)
        assert tpl["local_status"] == LOCAL_STATUS_SAVED
        assert tpl["sync_status"] == TELNYX_SYNC_NOT_SYNCED


def test_out_of_sync_after_local_edit():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type, category="MARKETING")
        components = json_module.loads(row.draft_components_json)
        row.telnyx_record_id = "telnyx-uuid"
        row.template_id = "telnyx-uuid"
        row.status = "APPROVED"
        row.components_json = row.draft_components_json
        from app.services.survey_whatsapp_template_service import _content_hash

        row.remote_content_hash = _content_hash(components)
        row.last_pushed_at = row.updated_at
        row.local_sync_status = "in_sync"
        db.add(row)
        db.commit()
        db.refresh(row)

        body = components[0]
        body["text"] = str(body.get("text") or "") + " Updated locally."
        SurveyWhatsappTemplateService.save_draft(db, row, {"components": components})
        row = SurveyWhatsappTemplateService.get_template(db, row.id)
        assert telnyx_sync_ui_label(row) == TELNYX_SYNC_OUT_OF_SYNC
        state = template_workflow_state(row)
        assert state["needs_resync"] is True
        assert state["sync_status"] == TELNYX_SYNC_OUT_OF_SYNC
