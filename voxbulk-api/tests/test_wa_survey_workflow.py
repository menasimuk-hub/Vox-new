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
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.organisation import Organisation
from app.models.user import User
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.services.survey_generation_service import SurveyGenerationService
from app.services.survey_step_bank_service import PACK_STEP_ROLES
from app.services.survey_results_service import SurveyResultsService
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_whatsapp_template_service import (
    ANONYMOUS_BODY_SENTENCE,
    ANONYMOUS_FOOTER,
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    VARIANT_ANONYMOUS,
    VARIANT_STANDARD,
    _apply_anonymous_wording,
    _validate_mobile_number,
    format_sync_summary,
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


def _link_template(
    db,
    survey_type: SurveyType,
    template: TelnyxWhatsappTemplate,
    *,
    usable_as_standard: bool = False,
    usable_as_anonymous: bool = False,
    is_default_standard: bool = False,
    is_default_anonymous: bool = False,
) -> SurveyTypeTemplate:
    return SurveyTypeTemplateService.upsert_mapping(
        db,
        survey_type_id=survey_type.id,
        template_id=template.id,
        usable_as_standard=usable_as_standard,
        usable_as_anonymous=usable_as_anonymous,
        is_default_standard=is_default_standard,
        is_default_anonymous=is_default_anonymous,
    )


def _approved_template(
    db,
    survey_type: SurveyType,
    *,
    variant: str = VARIANT_STANDARD,
    name: str | None = None,
    step_role: str = "start",
) -> TelnyxWhatsappTemplate:
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
    record_id = str(uuid.uuid4())
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=record_id,
        template_id=record_id,
        name=name or f"voxbulk_survey_{survey_type.slug}_{variant}",
        display_name=f"{survey_type.name} — {variant.title()}",
        language="en_US",
        category="MARKETING",
        status="APPROVED",
        variant_type=variant,
        step_role=step_role,
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
    db.flush()
    if variant == VARIANT_ANONYMOUS:
        _link_template(
            db,
            survey_type,
            row,
            usable_as_anonymous=True,
            is_default_anonymous=True,
        )
    else:
        _link_template(
            db,
            survey_type,
            row,
            usable_as_standard=True,
            is_default_standard=True,
        )
    db.refresh(row)
    return row


def _seed_step_bank(db, survey_type: SurveyType, *, variant: str = VARIANT_STANDARD) -> None:
    """Minimal 10-role step bank for generation tests."""
    now = datetime.utcnow()
    for role in PACK_STEP_ROLES:
        record_id = str(uuid.uuid4())
        status = "APPROVED" if role == "start" else "LOCAL_DRAFT"
        body = f"Step {role} for {{{{1}}}} at {{{{2}}}}."
        components = [
            {"type": "BODY", "text": body},
            {"type": "FOOTER", "text": "Reply STOP to opt out"},
        ]
        if role == "start":
            components.append({"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Start survey"}]})
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=record_id,
            template_id=record_id,
            name=f"voxbulk_survey_{survey_type.slug}_{role}",
            display_name=role.replace("_", " ").title(),
            language="en_US",
            category="MARKETING",
            status=status,
            variant_type=variant,
            step_role=role,
            body_preview=body[:60],
            components_json=json.dumps(components) if status == "APPROVED" else None,
            draft_components_json=json.dumps(components),
            example_values_json=json.dumps(["Alex"]),
            local_sync_status="in_sync" if status == "APPROVED" else "draft",
            active_for_survey=True,
            created_at=now,
            updated_at=now,
            synced_at=now,
        )
        db.add(row)
        db.flush()
        if variant == VARIANT_ANONYMOUS:
            _link_template(db, survey_type, row, usable_as_anonymous=True)
        else:
            _link_template(db, survey_type, row, usable_as_standard=True)


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


def test_prepare_components_for_telnyx_push_strips_invalid_body_example():
    from app.services.survey_whatsapp_template_service import prepare_components_for_telnyx_push

    raw = [
        {
            "type": "BODY",
            "text": "How was your visit?",
            "example": {"body_text": [[]]},
        },
        {"type": "FOOTER", "text": "Reply STOP to opt out"},
    ]
    prepared = prepare_components_for_telnyx_push(raw)
    body = next(c for c in prepared if c.get("type") == "BODY")
    assert body["example"]["body_text"] == [["Sample"]]


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

            def get(self, url, headers=None):
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
        assert captured["payload"]["category"] == "MARKETING"
        assert captured["payload"]["components"]


def test_push_to_telnyx_injects_body_example_when_missing(monkeypatch):
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        row.draft_components_json = json.dumps(
            [
                {"type": "BODY", "text": "How was the food quality on your visit? ⭐"},
                {"type": "FOOTER", "text": "Reply STOP to opt out"},
                {
                    "type": "BUTTONS",
                    "buttons": [
                        {"type": "QUICK_REPLY", "text": "Poor"},
                        {"type": "QUICK_REPLY", "text": "Okay"},
                        {"type": "QUICK_REPLY", "text": "Excellent"},
                    ],
                },
            ]
        )
        row.example_values_json = json.dumps([])
        db.add(row)
        db.commit()
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
                        "components": captured["payload"]["components"],
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

            def get(self, url, headers=None):
                return FakeResponse()

        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.httpx.Client",
            lambda *a, **k: FakeClient(),
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
            lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
        )
        SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        body = captured["payload"]["components"][0]
        assert body["type"] == "BODY"
        assert body["example"]["body_text"] == [["Sample"]]


def test_sync_content_hash_ignores_meta_only_body_example():
    from app.services.survey_whatsapp_template_service import (
        SYNC_IN_SYNC,
        SYNC_LOCAL_CHANGES,
        _sync_content_hash,
        _refresh_local_sync_status,
        telnyx_sync_ui_label,
        TELNYX_SYNC_PENDING,
    )

    draft = [{"type": "BODY", "text": "How was your visit?"}]
    remote = [
        {
            "type": "BODY",
            "text": "How was your visit?",
            "example": {"body_text": [["Sample"]]},
        }
    ]
    assert _sync_content_hash(draft) == _sync_content_hash(remote)

    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        row.telnyx_record_id = "telnyx-record-1"
        row.status = "PENDING"
        row.draft_components_json = json.dumps(draft)
        row.components_json = json.dumps(remote)
        row.remote_content_hash = _sync_content_hash(remote)
        db.add(row)
        db.commit()

        assert _refresh_local_sync_status(row) == SYNC_IN_SYNC
        assert telnyx_sync_ui_label(row) == TELNYX_SYNC_PENDING

        row.draft_components_json = json.dumps([{"type": "BODY", "text": "Changed body text"}])
        db.add(row)
        db.commit()
        assert _refresh_local_sync_status(row) == SYNC_LOCAL_CHANGES


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
        _seed_step_bank(db, survey_type)
        result = SurveyGenerationService.generate(
            db,
            survey_type_id=survey_type.id,
            variant=VARIANT_STANDARD,
            length="short",
        )
        assert result["page_count"] == 4
        assert len(result["page_roles"]) == 4
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
        _seed_step_bank(db, survey_type, variant=VARIANT_ANONYMOUS)
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


def test_format_sync_summary_no_matches():
    summary = format_sync_summary(
        {
            "ok": True,
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "remote_count": 12,
            "survey_matched": 0,
            "filter_description": "Only names containing survey",
        }
    )
    assert summary["severity"] == "warn"
    assert "no survey templates were found" in summary["message"].lower()


def test_validate_mobile_number():
    ok, err = _validate_mobile_number("+447700900123")
    assert ok == "+447700900123"
    assert err is None
    bad, err = _validate_mobile_number("not-a-phone")
    assert bad is None
    assert "valid mobile" in err.lower()


def test_send_test_blocks_unapproved_local_draft():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = _approved_template(db, survey_type)
        row.status = "LOCAL_DRAFT"
        row.telnyx_record_id = f"local-{uuid.uuid4().hex}"
        db.add(row)
        db.commit()
        with pytest.raises(SurveyWhatsappTemplateError, match="local draft"):
            SurveyWhatsappTemplateService.send_test_template(db, row, to_number="+447700900123")


def test_send_test_success(monkeypatch):
    from app.services.telnyx_messaging_service import TelnyxMessageResult

    def fake_send(*args, **kwargs):
        return TelnyxMessageResult(ok=True, status="queued", external_id="msg-123", detail=None, channel="whatsapp")

    monkeypatch.setattr(
        "app.services.telnyx_messaging_service.TelnyxMessagingService.send_whatsapp",
        fake_send,
    )
    monkeypatch.setattr(
        "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._messaging_org_id",
        lambda db: "org-1",
    )
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = _approved_template(db, survey_type)
        result = SurveyWhatsappTemplateService.send_test_template(db, row, to_number="+447700900123")
        assert result["success"] is True
        assert result["template_name"] == row.name
        assert result["to_number"] == "+447700900123"


def test_send_builder_flow_test_requires_session(monkeypatch):
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        welcome = _approved_template(db, survey_type, name="voxbulk_welcome_test", step_role="start")
        middle = _approved_template(db, survey_type, name="voxbulk_middle_test", step_role="yes_no")
        thank = _approved_template(db, survey_type, name="voxbulk_thank_test", step_role="completion")
        with pytest.raises(SurveyWhatsappTemplateError, match="Bulk template test send is disabled"):
            SurveyWhatsappTemplateService.send_builder_flow_test(
                db,
                template_ids=[welcome.id, middle.id, thank.id],
                to_number="+447700900123",
            )


def test_admin_wa_survey_api(app_client):
    from tests.test_agent_architecture import _headers

    headers, _org_id, _category_id = _headers(app_client)
    listed = app_client.get("/admin/wa-survey/types", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["types"]) >= 5

    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = _approved_template(db, survey_type)

    detail = app_client.get(f"/admin/wa-survey/templates/{row.id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["template"]["id"] == row.id
    assert isinstance(body.get("survey_types"), list)
    assert len(body["survey_types"]) >= 1


def test_one_template_mapped_to_multiple_survey_types():
    with get_sessionmaker()() as db:
        type_a = _seed_survey_type(db)
        type_b = SurveyTypeService.get_by_slug(db, "quick_feedback")
        assert type_b is not None
        shared = _approved_template(db, type_a, name="voxbulk_shared_survey_standard")
        _link_template(db, type_b, shared, usable_as_standard=True)
        count = SurveyTypeTemplateService.linked_survey_type_count(db, shared.id)
        assert count == 2
        mappings = SurveyTypeTemplateService.list_for_template(db, shared.id)
        assert len(mappings) == 2


def test_default_uniqueness_per_survey_type():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        first = _approved_template(db, survey_type, name="voxbulk_survey_cs_default_a")
        second = _approved_template(db, survey_type, name="voxbulk_survey_cs_default_b")
        SurveyTypeTemplateService.upsert_mapping(
            db,
            survey_type_id=survey_type.id,
            template_id=second.id,
            usable_as_standard=True,
            is_default_standard=True,
        )
        mappings = SurveyTypeTemplateService.list_for_survey_type(db, survey_type.id)
        defaults = [m for m in mappings if m.is_default_standard]
        assert len(defaults) == 1
        assert defaults[0].template_id == second.id
        first_mapping = next(m for m in mappings if m.template_id == first.id)
        assert first_mapping.is_default_standard is False


def test_shared_source_edit_affects_all_linked_types():
    with get_sessionmaker()() as db:
        type_a = _seed_survey_type(db)
        type_b = SurveyTypeService.get_by_slug(db, "quick_feedback")
        assert type_b is not None
        shared = _approved_template(db, type_a, name="voxbulk_shared_source_standard")
        _link_template(db, type_b, shared, usable_as_standard=True, is_default_standard=True)
        updated_components = json.loads(shared.draft_components_json)
        updated_components[0]["text"] = "Hi {{1}}, shared wording updated."
        SurveyWhatsappTemplateService.save_draft(db, shared, {"components": updated_components})
        preview = SurveyWhatsappTemplateService.build_preview(db, shared, first_name="Alex")
        assert "shared wording updated" in preview["rendered_body"]
        assert db.execute(select(func.count()).select_from(TelnyxWhatsappTemplate)).scalar_one() == 1


def test_mapping_changes_do_not_duplicate_templates():
    with get_sessionmaker()() as db:
        type_a = _seed_survey_type(db)
        type_b = SurveyTypeService.get_by_slug(db, "quick_feedback")
        assert type_b is not None
        shared = _approved_template(db, type_a, name="voxbulk_shared_no_dup")
        before = db.execute(select(func.count()).select_from(TelnyxWhatsappTemplate)).scalar_one()
        SurveyWhatsappTemplateService.update_template_mappings(
            db,
            shared.id,
            [
                {
                    "survey_type_id": type_a.id,
                    "usable_as_standard": True,
                    "is_default_standard": True,
                },
                {
                    "survey_type_id": type_b.id,
                    "usable_as_standard": True,
                },
            ],
        )
        after = db.execute(select(func.count()).select_from(TelnyxWhatsappTemplate)).scalar_one()
        assert before == after == 1
        assert SurveyTypeTemplateService.linked_survey_type_count(db, shared.id) == 2


def test_generation_uses_explicit_default_mapping(monkeypatch):
    monkeypatch.setattr(
        "app.services.survey_generation_service.generate_survey_script",
        lambda *a, **k: {"whatsapp_questions": [], "script_text": "INTRO", "system_prompt": "Be polite"},
    )
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        _seed_step_bank(db, survey_type)
        name_match = _approved_template(
            db,
            survey_type,
            name=f"voxbulk_survey_{survey_type.slug}_standard",
            step_role="start",
        )
        explicit_default = _approved_template(
            db,
            survey_type,
            name="voxbulk_shared_explicit_default",
            step_role="start",
        )
        SurveyTypeTemplateService.upsert_mapping(
            db,
            survey_type_id=survey_type.id,
            template_id=name_match.id,
            usable_as_standard=True,
            is_default_standard=False,
        )
        SurveyTypeTemplateService.upsert_mapping(
            db,
            survey_type_id=survey_type.id,
            template_id=explicit_default.id,
            usable_as_standard=True,
            is_default_standard=True,
        )
        result = SurveyGenerationService.generate(
            db,
            survey_type_id=survey_type.id,
            variant=VARIANT_STANDARD,
            length="short",
        )
        assert result["wa_template_id"] == explicit_default.id
