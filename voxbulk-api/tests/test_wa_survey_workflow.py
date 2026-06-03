"""WA Survey types, template library, sync, preview, and generation."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from app.core.database import get_sessionmaker
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.organisation import Organisation
from app.models.user import User
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.services.survey_generation_service import SurveyGenerationService
from app.services.survey_results_service import SurveyResultsService
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_whatsapp_template_service import (
    ANONYMOUS_BODY_SENTENCE,
    ANONYMOUS_FOOTER,
    SurveyWhatsappTemplateService,
    VARIANT_ANONYMOUS,
    VARIANT_STANDARD,
    _apply_anonymous_wording,
)


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _seed_survey_type(db) -> SurveyType:
    SurveyTypeService.ensure_defaults(db)
    row = SurveyTypeService.get_by_slug(db, "customer_satisfaction")
    assert row is not None
    return row


def _approved_template(db, survey_type: SurveyType, *, variant: str = VARIANT_STANDARD) -> TelnyxWhatsappTemplate:
    components = [
        {
            "type": "BODY",
            "text": "Hi {{1}}, please share feedback about our service.",
            "example": {"body_text": [["Alex"]]},
        },
        {"type": "FOOTER", "text": "Reply STOP to opt out"},
        {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Start survey"}]},
    ]
    now = datetime.utcnow()
    local_id = f"local-{uuid.uuid4().hex}"
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=local_id,
        template_id=local_id,
        name=f"voxbulk_survey_{survey_type.slug}_{variant}",
        display_name=f"{survey_type.name} — {variant.title()}",
        language="en_US",
        category="MARKETING",
        status="APPROVED",
        survey_type_id=survey_type.id,
        variant_type=variant,
        body_preview="Hi {{1}}",
        components_json=json.dumps(components),
        draft_components_json=json.dumps(components),
        example_values_json=json.dumps(["Alex"]),
        local_sync_status="in_sync",
        active_for_survey=True,
        created_at=now,
        updated_at=now,
        synced_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_survey_types_seeded_and_listed():
    with get_sessionmaker()() as db:
        types = SurveyTypeService.list_types(db)
        assert len(types) >= 5
        slugs = {t["slug"] for t in types}
        assert "customer_satisfaction" in slugs
        assert "quick_feedback" in slugs


def test_survey_type_update_persists():
    with get_sessionmaker()() as db:
        row = _seed_survey_type(db)
        updated = SurveyTypeService.update_type(
            db,
            row,
            {"description": "Updated description", "default_length": "short", "supports_anonymous": True},
        )
        assert updated.description == "Updated description"
        assert updated.default_length == "short"


def test_survey_type_create_persists():
    with get_sessionmaker()() as db:
        created = SurveyTypeService.create_type(
            db,
            {"name": "Post visit feedback", "description": "Custom local type"},
        )
        assert created.name == "Post visit feedback"
        assert created.slug == "post_visit_feedback"
        again = SurveyTypeService.get_by_slug(db, "post_visit_feedback")
        assert again is not None
        assert again.id == created.id


def test_clone_as_anonymous_applies_wording():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        parent = _approved_template(db, survey_type, variant=VARIANT_STANDARD)
        anon = SurveyWhatsappTemplateService.clone_as_anonymous(db, parent)
        components = json.loads(anon.draft_components_json)
        body = next(c["text"] for c in components if c["type"] == "BODY")
        footer = next(c["text"] for c in components if c["type"] == "FOOTER")
        assert ANONYMOUS_BODY_SENTENCE in body
        assert footer == ANONYMOUS_FOOTER
        assert anon.variant_type == VARIANT_ANONYMOUS
        assert anon.parent_template_id == parent.id


def test_apply_anonymous_wording_helper():
    components = [{"type": "BODY", "text": "Hello {{1}}"}]
    out = _apply_anonymous_wording(components)
    body = next(c["text"] for c in out if c["type"] == "BODY")
    assert ANONYMOUS_BODY_SENTENCE in body


def test_sync_imports_only_survey_named_templates(monkeypatch):
    remote = [
        {
            "id": "rec-survey-1",
            "template_id": "111",
            "name": "voxbulk_survey_customer_satisfaction_standard",
            "language": "en_US",
            "status": "APPROVED",
            "category": "MARKETING",
            "components": [{"type": "BODY", "text": "Hi {{1}}", "example": {"body_text": [["Alex"]]}}],
        },
        {
            "id": "rec-sales-1",
            "template_id": "222",
            "name": "voxbulk_sales_offer",
            "language": "en_US",
            "status": "APPROVED",
            "components": [{"type": "BODY", "text": "Offer {{1}}"}],
        },
    ]
    monkeypatch.setattr(
        "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_from_telnyx",
        lambda db: remote,
    )
    with get_sessionmaker()() as db:
        SurveyTypeService.ensure_defaults(db)
        summary = SurveyWhatsappTemplateService.sync_from_telnyx(db)
        assert summary["survey_matched"] == 1
        assert summary["imported"] == 1
        rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars())
        assert len(rows) == 1
        assert "survey" in rows[0].name.lower()


def test_sync_updates_existing_not_duplicated(monkeypatch):
    remote = [
        {
            "id": "rec-survey-dup",
            "template_id": "333",
            "name": "voxbulk_survey_quick_feedback_standard",
            "language": "en_US",
            "status": "APPROVED",
            "category": "UTILITY",
            "components": [{"type": "BODY", "text": "Updated body {{1}}", "example": {"body_text": [["Sam"]]}}],
        }
    ]
    monkeypatch.setattr(
        "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_from_telnyx",
        lambda db: remote,
    )
    with get_sessionmaker()() as db:
        SurveyTypeService.ensure_defaults(db)
        first = SurveyWhatsappTemplateService.sync_from_telnyx(db)
        second = SurveyWhatsappTemplateService.sync_from_telnyx(db)
        assert first["imported"] == 1
        assert second["imported"] == 0
        assert second["updated"] == 1
        count = db.execute(select(func.count()).select_from(TelnyxWhatsappTemplate)).scalar_one()
        assert count == 1


def test_push_to_telnyx_builds_payload(monkeypatch):
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "data": {
                        "id": "telnyx-new-id",
                        "template_id": "999",
                        "status": "PENDING",
                        "components": json.loads(row.draft_components_json),
                    }
                }

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, headers=None, json=None):
                captured["payload"] = json
                return FakeResponse()

        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.httpx.Client",
            lambda *a, **k: FakeClient(),
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
            lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
        )
        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        assert result["ok"] is True
        assert captured["payload"]["waba_id"] == "waba-123"
        assert captured["payload"]["components"]


def test_preview_renders_placeholders():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = _approved_template(db, survey_type)
        preview = SurveyWhatsappTemplateService.build_preview(db, row, first_name="Alex")
        assert "Alex" in preview["rendered_body"]
        assert preview["buttons"]
        assert preview["sync_status"]


def test_generation_chooses_template_and_question_count(monkeypatch):
    monkeypatch.setattr(
        "app.services.survey_generation_service.generate_survey_script",
        lambda *a, **k: {"whatsapp_questions": [], "script_text": "INTRO\nHello", "system_prompt": "Be polite"},
    )
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        _approved_template(db, survey_type, variant=VARIANT_STANDARD)
        result = SurveyGenerationService.generate(
            db,
            survey_type_id=survey_type.id,
            variant=VARIANT_STANDARD,
            length="short",
        )
        assert result["question_count"] == 4
        assert result["wa_template_id"]
        assert len(result["flow_steps"]) >= 4
        assert result["template_preview"]["rendered_body"]


def test_anonymous_generation_flags_privacy(monkeypatch):
    monkeypatch.setattr(
        "app.services.survey_generation_service.generate_survey_script",
        lambda *a, **k: {"whatsapp_questions": [], "script_text": "", "system_prompt": ""},
    )
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        _approved_template(db, survey_type, variant=VARIANT_ANONYMOUS)
        result = SurveyGenerationService.generate(
            db,
            survey_type_id=survey_type.id,
            variant=VARIANT_ANONYMOUS,
            length="standard",
        )
        assert result["anonymous_responses"] is True
        assert result["allow_follow_up"] is False


def test_results_hide_names_for_anonymous_order():
    with get_sessionmaker()() as db:
        org = Organisation(name="Anon Org")
        user = User(email=f"anon-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("x"), is_active=True)
        db.add(org)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
        order = ServiceOrder(
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="Anon survey",
            status="completed",
            config_json=json.dumps({"anonymous_responses": True, "delivery": "whatsapp"}),
        )
        db.add(order)
        db.flush()
        db.add(
            ServiceOrderRecipient(
                order_id=order.id,
                row_number=1,
                name="Secret Person",
                phone="+447700900001",
                status="completed",
            )
        )
        db.commit()
        anon_payload = SurveyResultsService.get_results(db, order, anonymous=True)
        named_payload = SurveyResultsService.get_results(db, order, anonymous=False)
        assert anon_payload["respondents"] == []
        assert len(named_payload["respondents"]) == 1


def test_admin_wa_survey_api(app_client):
    from tests.test_agent_architecture import _headers

    headers, _org_id, _category_id = _headers(app_client)
    listed = app_client.get("/admin/wa-survey/types", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["types"]) >= 5
