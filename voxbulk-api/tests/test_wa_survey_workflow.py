"""WA Survey types, template library, sync, preview, and generation."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import httpx
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


def test_fix_survey_template_draft_body_variables_clears_static_example():
    from app.services.survey_whatsapp_template_service import fix_survey_template_draft_body_variables

    raw = [
        {
            "type": "BODY",
            "text": "How was your viewing experience?",
            "example": {"body_text": [["Sample"]]},
        },
        {"type": "FOOTER", "text": "Reply STOP to opt out"},
    ]
    fixed = fix_survey_template_draft_body_variables(raw)
    body = next(c for c in fixed if c.get("type") == "BODY")
    assert "example" not in body
    assert body["text"] == "How was your viewing experience?"


def test_fix_survey_template_draft_body_variables_keeps_variable_examples():
    from app.services.survey_whatsapp_template_service import fix_survey_template_draft_body_variables

    raw = [{"type": "BODY", "text": "Hi {{1}}, thanks for visiting."}]
    fixed = fix_survey_template_draft_body_variables(raw)
    body = next(c for c in fixed if c.get("type") == "BODY")
    assert body["example"]["body_text"] == [["Alex"]]


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
    assert "example" not in body
    assert body["text"] == "How was your visit?"


def test_prepare_components_for_telnyx_push_injects_example_for_variables():
    from app.services.survey_whatsapp_template_service import prepare_components_for_telnyx_push

    raw = [{"type": "BODY", "text": "Hi {{1}}, thanks for visiting."}]
    prepared = prepare_components_for_telnyx_push(raw)
    body = next(c for c in prepared if c.get("type") == "BODY")
    assert body["example"]["body_text"] == [["Alex"]]


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
        assert captured["payload"]["category"] == "UTILITY"
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
        assert "example" not in body


def test_push_to_telnyx_links_remote_then_refreshes_when_pending(monkeypatch):
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        row.name = "voxbulk_survey_food_quality_hospitality_food_food_quality_rating"
        row.draft_components_json = json.dumps(
            [
                {"type": "BODY", "text": "How was the food quality on your visit?"},
                {"type": "FOOTER", "text": "Reply STOP to opt out"},
            ]
        )
        db.add(row)
        db.commit()

        remote_item = {
            "id": "remote-uuid-1",
            "template_id": "888",
            "name": row.name,
            "language": "en_GB",
            "status": "PENDING",
            "category": "MARKETING",
            "components": [{"type": "BODY", "text": "How was the food quality on your visit?"}],
        }
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_from_telnyx",
            lambda db: [remote_item],
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_template_by_record_id",
            lambda db, rid: {**remote_item, "id": rid, "status": "APPROVED"},
        )

        patch_called = {"value": False}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def patch(self, url, headers=None, json=None):
                patch_called["value"] = True
                raise AssertionError("PATCH must not run for PENDING templates")

            def post(self, url, headers=None, json=None):
                raise AssertionError("POST must not run when remote PENDING template was linked")

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
        assert patch_called["value"] is False
        assert result["approval_status"] == "APPROVED"
        assert result["sync_branch"] == "status_refresh_only"
        assert result["telnyx_request_mode"] == "status_refresh_only"
        db.refresh(row)
        assert row.telnyx_record_id == "remote-uuid-1"


def test_push_to_telnyx_rejected_existing_remote_resubmits_via_post(monkeypatch):
    from app.services.survey_whatsapp_template_service import _loads, _sync_content_hash

    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        row.name = "voxbulk_survey_rejected_patch_example"
        row.telnyx_record_id = "remote-rejected-1"
        row.template_id = "888"
        row.status = "REJECTED"
        row.draft_components_json = json.dumps(
            [
                {"type": "BODY", "text": "Updated body after rejection"},
                {"type": "FOOTER", "text": "Reply STOP to opt out"},
            ]
        )
        row.components_json = json.dumps([{"type": "BODY", "text": "Old rejected body"}])
        row.remote_content_hash = _sync_content_hash(_loads(row.components_json))
        db.add(row)
        db.commit()

        captured: dict[str, Any] = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "data": {
                        "id": "remote-rejected-1",
                        "template_id": "888",
                        "status": "PENDING",
                        "components": captured["post_payload"]["components"],
                    }
                }

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def patch(self, url, headers=None, json=None):
                raise AssertionError("PATCH must not run for rejected recovery — use POST")

            def post(self, url, headers=None, json=None):
                captured["post_payload"] = json
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
        assert result["sync_branch"] == "rejected_recovery"
        assert result["telnyx_request_mode"] == "create_or_update_template"
        body = captured["post_payload"]["components"][0]
        assert "example" not in body


def test_push_to_telnyx_approved_draft_diff_blocks_without_force():
    from app.services.survey_whatsapp_template_service import (
        SurveyWhatsappTemplateError,
        _loads,
        _sync_content_hash,
    )

    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        row.telnyx_record_id = "remote-approved-blocked"
        row.template_id = "999"
        row.status = "APPROVED"
        row.draft_components_json = json.dumps([{"type": "BODY", "text": "Updated utility body"}])
        row.components_json = json.dumps([{"type": "BODY", "text": "Original approved body"}])
        row.remote_content_hash = _sync_content_hash(_loads(row.components_json))
        db.add(row)
        db.commit()

        try:
            SurveyWhatsappTemplateService.push_to_telnyx(db, row)
            raise AssertionError("expected approved-update guard")
        except SurveyWhatsappTemplateError as exc:
            assert "APPROVED on Meta" in str(exc)


def test_push_to_telnyx_approved_draft_diff_resubmits_with_force(monkeypatch):
    from app.services.survey_whatsapp_template_service import (
        SYNC_BRANCH_APPROVED_UPDATE,
        _loads,
        _sync_content_hash,
    )

    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        row.telnyx_record_id = "remote-approved-force"
        row.template_id = "1000"
        row.status = "APPROVED"
        row.category = "UTILITY"
        row.draft_components_json = json.dumps(
            [{"type": "BODY", "text": "😊 Following your recent visit, how was it?"}]
        )
        row.components_json = json.dumps([{"type": "BODY", "text": "😊 How was it?"}])
        row.remote_content_hash = _sync_content_hash(_loads(row.components_json))
        db.add(row)
        db.commit()

        captured: dict[str, Any] = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "data": {
                        "id": "remote-approved-force",
                        "template_id": "1000",
                        "status": "PENDING",
                        "category": "UTILITY",
                        "components": captured["patch_payload"]["components"],
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
                raise AssertionError("POST must not run for approved force update — use PATCH")

            def patch(self, url, headers=None, json=None):
                captured["patch_payload"] = json
                return FakeResponse()

        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.httpx.Client",
            lambda *a, **k: FakeClient(),
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
            lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
        )

        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row, force_approved_update=True)
        assert result["ok"] is True
        assert result["sync_branch"] == SYNC_BRANCH_APPROVED_UPDATE
        assert result["telnyx_request_mode"] == "patch_template"
        assert captured["patch_payload"]["category"] == "UTILITY"


def test_resolve_template_sync_branch_pending_remote_is_status_refresh():
    from app.services.survey_whatsapp_template_service import (
        SYNC_BRANCH_STATUS_REFRESH,
        resolve_template_sync_branch,
    )

    row = TelnyxWhatsappTemplate(
        telnyx_record_id="remote-1",
        template_id="1",
        name="voxbulk_survey_test",
        status="PENDING",
        draft_components_json=json.dumps([{"type": "BODY", "text": "Hello"}]),
        components_json=json.dumps([{"type": "BODY", "text": "Hello"}]),
    )
    branch, err = resolve_template_sync_branch(row, [{"type": "BODY", "text": "Hello"}])
    assert branch == SYNC_BRANCH_STATUS_REFRESH
    assert err is None


def test_resolve_template_sync_branch_local_draft_with_remote_id_is_status_refresh():
    from app.services.survey_whatsapp_template_service import (
        SYNC_BRANCH_STATUS_REFRESH,
        resolve_template_sync_branch,
    )

    row = TelnyxWhatsappTemplate(
        telnyx_record_id="remote-pending-1",
        template_id="1",
        name="voxbulk_survey_viewing_experience_abc_54a96f",
        status="LOCAL_DRAFT",
        draft_components_json=json.dumps([{"type": "BODY", "text": "How was the viewing?"}]),
        components_json=json.dumps([{"type": "BODY", "text": "How was the viewing?"}]),
    )
    branch, err = resolve_template_sync_branch(row, [{"type": "BODY", "text": "How was the viewing?"}])
    assert branch == SYNC_BRANCH_STATUS_REFRESH
    assert err is None


def test_push_recovers_from_missing_body_example_when_remote_pending(monkeypatch):
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        row.name = "voxbulk_survey_viewing_experience_abc_54a96f"
        row.draft_components_json = json.dumps(
            [
                {"type": "BODY", "text": "How was the viewing experience?"},
                {"type": "FOOTER", "text": "Reply STOP to opt out"},
            ]
        )
        db.add(row)
        db.commit()

        remote_item = {
            "id": "remote-uuid-viewing",
            "template_id": "901",
            "name": row.name,
            "language": "en_GB",
            "status": "PENDING",
            "category": "UTILITY",
            "components": [{"type": "BODY", "text": "How was the viewing experience?"}],
        }
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_from_telnyx",
            lambda db: [remote_item],
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_template_by_record_id",
            lambda db, rid: {**remote_item, "id": rid, "status": "APPROVED"},
        )

        post_calls = {"count": 0}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, headers=None, json=None):
                post_calls["count"] += 1
                raise httpx.HTTPStatusError(
                    "meta rejected",
                    request=httpx.Request("POST", url),
                    response=httpx.Response(
                        422,
                        json={
                            "errors": [
                                {
                                    "detail": (
                                        'meta api error: {"error":{"error_subcode":2388043,'
                                        '"error_user_msg":"missing example"}}'
                                    )
                                }
                            ]
                        },
                    ),
                )

        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.httpx.Client",
            lambda *a, **k: FakeClient(),
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
            lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
        )

        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        assert post_calls["count"] == 0
        assert result["ok"] is True
        assert result["sync_branch"] == "status_refresh_only"
        db.refresh(row)
        assert row.telnyx_record_id == "remote-uuid-viewing"


def test_push_all_for_survey_type_reuses_prefetched_remote_list(monkeypatch):
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        row.name = "voxbulk_survey_bulk_prefetch_test"
        body = [{"type": "BODY", "text": "Bulk prefetch test"}]
        row.draft_components_json = json.dumps(body)
        db.add(row)
        db.commit()

        fetch_calls = {"count": 0}

        def fake_fetch(db):
            fetch_calls["count"] += 1
            return [
                {
                    "id": "remote-pending-bulk",
                    "template_id": "555",
                    "name": row.name,
                    "language": "en_GB",
                    "status": "PENDING",
                    "components": body,
                }
            ]

        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_from_telnyx",
            fake_fetch,
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_template_by_record_id",
            lambda db, rid: {
                "id": rid,
                "template_id": "555",
                "name": row.name,
                "language": "en_GB",
                "status": "APPROVED",
                "components": body,
            },
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
            lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
        )

        prefetched = [{"id": "remote-pending-bulk", "name": row.name, "language": "en_GB", "status": "PENDING"}]
        summary = SurveyWhatsappTemplateService.push_all_for_survey_type(
            db,
            survey_type.id,
            remote_items=prefetched,
        )
        assert summary["pushed"] == 1
        assert fetch_calls["count"] == 0


def test_push_to_telnyx_approved_in_sync_refreshes_only(monkeypatch):
    from app.services.survey_whatsapp_template_service import _sync_content_hash

    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        row = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=survey_type)
        body_text = "How was your visit?"
        draft = [{"type": "BODY", "text": body_text}]
        remote = [
            {
                "type": "BODY",
                "text": body_text,
                "example": {"body_text": [["Sample"]]},
            }
        ]
        row.telnyx_record_id = "telnyx-approved-1"
        row.template_id = "777"
        row.status = "APPROVED"
        row.draft_components_json = json.dumps(draft)
        row.components_json = json.dumps(remote)
        row.remote_content_hash = _sync_content_hash(remote)
        db.add(row)
        db.commit()

        patch_called = {"value": False}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def patch(self, url, headers=None, json=None):
                patch_called["value"] = True
                raise AssertionError("PATCH must not run for APPROVED templates")

            def post(self, url, headers=None, json=None):
                raise AssertionError("POST must not run for APPROVED templates")

        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.httpx.Client",
            lambda *a, **k: FakeClient(),
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.TelnyxWhatsappTemplateSyncService.fetch_template_by_record_id",
            lambda db, rid: {
                "id": rid,
                "template_id": "777",
                "status": "APPROVED",
                "components": remote,
            },
        )
        monkeypatch.setattr(
            "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
            lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
        )

        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        assert patch_called["value"] is False
        assert result["approval_status"] == "APPROVED"
        assert result["sync_branch"] == "status_refresh_only"
        assert result["telnyx_request_mode"] == "status_refresh_only"


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


def test_admin_detail_shows_hidden_templates_but_dashboard_library_hides_them(app_client):
    from tests.test_agent_architecture import _headers

    headers, _org_id, _category_id = _headers(app_client)
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        active_tpl = _approved_template(db, survey_type, name="voxbulk_cs_visible", step_role="yes_no")
        hidden_tpl = _approved_template(db, survey_type, name="voxbulk_cs_hidden", step_role="rating")
        hidden_tpl.active_for_survey = False
        db.add(hidden_tpl)
        db.commit()
        db.refresh(active_tpl)
        db.refresh(hidden_tpl)
        survey_type_id = survey_type.id
        active_id = active_tpl.id
        hidden_id = hidden_tpl.id

    admin_detail = app_client.get(f"/admin/wa-survey/types/{survey_type_id}", headers=headers)
    assert admin_detail.status_code == 200
    admin_template_ids = {int(t["id"]) for t in admin_detail.json().get("templates") or []}
    assert active_id in admin_template_ids
    assert hidden_id in admin_template_ids

    library = app_client.get(
        f"/dashboard/service-scripts/wa-survey/types/{survey_type_id}/library-templates?privacy_mode=off",
        headers=headers,
    )
    assert library.status_code == 200
    dashboard_template_ids = {int(t["id"]) for t in library.json().get("templates") or []}
    assert active_id in dashboard_template_ids
    assert hidden_id not in dashboard_template_ids


def test_dashboard_wa_type_list_hides_types_without_active_templates(app_client):
    from tests.test_agent_architecture import _headers

    headers, _org_id, _category_id = _headers(app_client)
    with get_sessionmaker()() as db:
        type_visible = _seed_survey_type(db)
        type_hidden = SurveyTypeService.get_by_slug(db, "quick_feedback")
        assert type_hidden is not None
        visible_tpl = _approved_template(db, type_visible, name="voxbulk_cs_visible_only", step_role="yes_no")
        hidden_tpl = _approved_template(db, type_hidden, name="voxbulk_qf_hidden_only", step_role="rating")
        hidden_tpl.active_for_survey = False
        db.add(hidden_tpl)
        db.commit()
        db.refresh(visible_tpl)
        industry_id = type_visible.industry_id
        visible_id = type_visible.id
        hidden_id = type_hidden.id

    listed = app_client.get(
        f"/dashboard/service-scripts/wa-survey/types?industry_id={industry_id}",
        headers=headers,
    )
    assert listed.status_code == 200
    type_ids = {str(t["id"]) for t in listed.json().get("types") or []}
    assert visible_id in type_ids
    assert hidden_id not in type_ids


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
