"""WA Survey step bank selection (4–6 pages from 10-template pack)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.core.database import get_sessionmaker
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_generation_service import SurveyGenerationService
from app.services.survey_step_bank_service import (
    AUTO_MIDDLE_PRIORITY,
    MIDDLE_STEP_ROLES,
    PACK_STEP_ROLES,
    SurveyStepBankService,
    auto_select_middle_roles,
    build_page_roles,
    load_step_bank,
    normalize_step_role,
    validate_survey_pages,
)
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_whatsapp_template_service import VARIANT_STANDARD


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _seed_survey_type(db):
    SurveyTypeService.ensure_defaults(db)
    row = SurveyTypeService.get_by_slug(db, "customer_satisfaction")
    assert row is not None
    return row


def _link(db, survey_type, template, **kwargs):
    return SurveyTypeTemplateService.upsert_mapping(
        db,
        survey_type_id=survey_type.id,
        template_id=template.id,
        usable_as_standard=True,
        **kwargs,
    )


def _template_for_role(db, survey_type, role: str, *, status: str = "LOCAL_DRAFT", is_default: bool = False):
    now = datetime.utcnow()
    record_id = str(uuid.uuid4())
    body = f"Body for {role} — hi {{{{1}}}}, ref {{{{3}}}}."
    if role == "start":
        body = "Hi {{1}}, {{2}} would love your feedback. Tap below. Ref {{3}}."
        status = "APPROVED"
    components = [
        {"type": "BODY", "text": body},
        {"type": "FOOTER", "text": "Reply STOP to opt out"},
    ]
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=record_id,
        template_id=record_id,
        name=f"voxbulk_survey_{survey_type.slug}_{role}",
        display_name=role.replace("_", " ").title(),
        language="en_US",
        category="MARKETING",
        status=status,
        variant_type=VARIANT_STANDARD,
        step_role=role,
        body_preview=body[:80],
        draft_components_json=json.dumps(components),
        example_values_json=json.dumps(["Alex", "Northgate", "https://example.com/s/1"]),
        local_sync_status="in_sync" if status == "APPROVED" else "draft",
        active_for_survey=True,
        created_at=now,
        updated_at=now,
        synced_at=now,
    )
    db.add(row)
    db.flush()
    _link(db, survey_type, row, is_default_standard=is_default)
    return row


def _seed_full_bank(db, survey_type):
    rows = {}
    for role in PACK_STEP_ROLES:
        rows[role] = _template_for_role(db, survey_type, role)
    return rows


def test_normalize_step_role_aliases():
    assert normalize_step_role("intro") == "start"
    assert normalize_step_role("closing") == "completion"
    assert normalize_step_role("yesno") == "yes_no"


def test_validate_survey_pages_rules():
    assert not validate_survey_pages(["start", "rating", "helpfulness", "completion"], page_count=4)
    assert "First page must be start" in validate_survey_pages(["rating", "helpfulness", "reason", "completion"], page_count=4)[0]
    assert "Last page must be completion" in validate_survey_pages(["start", "rating", "helpfulness", "reason"], page_count=4)[0]
    assert any("Duplicate" in e for e in validate_survey_pages(["start", "rating", "rating", "completion"], page_count=4))
    assert any("4" in e and "6" in e for e in validate_survey_pages(["start", "rating", "completion"], page_count=3))


def test_auto_select_middle_roles_respects_page_count():
    bank = {role: {"step_role": role} for role in PACK_STEP_ROLES}
    assert auto_select_middle_roles(4, bank) == list(AUTO_MIDDLE_PRIORITY[:2])
    assert auto_select_middle_roles(6, bank) == list(AUTO_MIDDLE_PRIORITY[:4])


def test_build_page_roles_always_bookends():
    bank = {role: {"step_role": role} for role in PACK_STEP_ROLES}
    roles = build_page_roles(page_count=5, bank_by_role=bank, auto_select=True)
    assert roles[0] == "start"
    assert roles[-1] == "completion"
    assert len(roles) == 5


def test_compose_survey_returns_four_to_six_pages():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        _seed_full_bank(db, survey_type)
        for count in (4, 5, 6):
            composed = SurveyStepBankService.compose_survey(
                db,
                survey_type=survey_type,
                page_count=count,
                auto_select=True,
            )
            assert len(composed["page_roles"]) == count
            assert len(composed["pages"]) == count
            assert composed["start_template_id"]


def test_generation_uses_step_bank_not_all_ten(monkeypatch):
    monkeypatch.setattr(
        "app.services.survey_generation_service.generate_survey_script",
        lambda *a, **k: {"whatsapp_questions": [], "script_text": "INTRO", "system_prompt": ""},
    )
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        _seed_full_bank(db, survey_type)
        result = SurveyGenerationService.generate(
            db,
            survey_type_id=survey_type.id,
            page_count=5,
            auto_select_steps=True,
        )
        assert result["page_count"] == 5
        assert len(result["page_roles"]) == 5
        assert result["page_roles"][0] == "start"
        assert result["page_roles"][-1] == "completion"
        assert len(result["pages"]) == 5


def test_manual_step_selection_order():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        _seed_full_bank(db, survey_type)
        manual = ["start", "improvement", "yes_no", "reason", "completion"]
        composed = SurveyStepBankService.compose_survey(
            db,
            survey_type=survey_type,
            page_count=5,
            auto_select=False,
            selected_step_roles=manual,
        )
        assert composed["page_roles"] == manual


def test_start_default_mapping_preferred():
    with get_sessionmaker()() as db:
        survey_type = _seed_survey_type(db)
        _seed_full_bank(db, survey_type)
        alt_start = _template_for_role(db, survey_type, "start", status="APPROVED", is_default=False)
        default_start = _template_for_role(
            db,
            survey_type,
            "start",
            status="APPROVED",
            is_default=True,
        )
        bank = load_step_bank(db, survey_type_id=survey_type.id)
        assert bank["by_role"]["start"]["template_id"] == default_start.id
        assert bank["by_role"]["start"]["template_id"] != alt_start.id
