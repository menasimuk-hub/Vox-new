"""Simulator deep-link prefill from saved survey type templates."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_flow_constants import FLOW_ENGINE_LINEAR
from app.services.survey_simulator_service import SurveySimulatorService
from app.services.survey_step_bank_service import PACK_STEP_ROLES
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_whatsapp_template_service import VARIANT_STANDARD


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        PlatformCatalogService.ensure_defaults(session)
        IndustryService.ensure_defaults(session)
        yield session
    finally:
        session.close()


def _survey_type(db) -> SurveyType:
    ind = db.execute(select(Industry).limit(1)).scalar_one()
    st = SurveyType(
        id=str(uuid.uuid4()),
        industry_id=ind.id,
        slug=f"sim-{uuid.uuid4().hex[:6]}",
        name="Sim Prefill Test",
        description="",
        is_active=True,
        default_length="standard",
        min_length=4,
        max_length=6,
        supports_anonymous=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(st)
    db.commit()
    return st


def test_prefill_defaults_linear_without_published_flow(db):
    st = _survey_type(db)
    data = SurveySimulatorService.prefill_for_survey_type(db, survey_type_id=st.id, privacy_mode="off")
    assert data["survey_type_id"] == st.id
    assert data["flow_engine"] == FLOW_ENGINE_LINEAR
    assert data["flow_definition_id"] is None
    assert data["use_saved_templates"] is True
    assert data["can_start_simulation"] is False
    assert any("start template" in e.lower() for e in data["blocking_errors"])


def _link_template(db, survey_type: SurveyType, template: TelnyxWhatsappTemplate) -> None:
    SurveyTypeTemplateService.upsert_mapping(
        db,
        survey_type_id=survey_type.id,
        template_id=template.id,
        usable_as_standard=True,
        is_default_standard=True,
    )


def _seed_bank_with_local_draft_start(db, survey_type: SurveyType) -> None:
    now = datetime.utcnow()
    for role in PACK_STEP_ROLES:
        record_id = str(uuid.uuid4())
        status = "LOCAL_DRAFT" if role == "start" else "APPROVED"
        body = f"Body for {role} — hi {{{{1}}}}."
        if role == "start":
            body = "Hi {{1}}, please tap below to begin the survey."
        row = TelnyxWhatsappTemplate(
            telnyx_record_id=record_id,
            template_id=record_id,
            name=f"sim_{survey_type.slug}_{role}",
            display_name=role.replace("_", " ").title(),
            language="en_US",
            category="MARKETING",
            status=status,
            variant_type=VARIANT_STANDARD,
            survey_type_id=survey_type.id,
            step_role=role,
            body_preview=body[:80],
            draft_components_json=json.dumps([{"type": "BODY", "text": body}]),
            example_values_json=json.dumps(["Alex"]),
            local_sync_status="draft",
            active_for_survey=True,
            created_at=now,
            updated_at=now,
            synced_at=now,
        )
        db.add(row)
        db.flush()
        _link_template(db, survey_type, row)
    db.commit()


def test_prefill_allows_local_draft_start_for_simulator(db):
    st = _survey_type(db)
    _seed_bank_with_local_draft_start(db, st)
    data = SurveySimulatorService.prefill_for_survey_type(db, survey_type_id=st.id, privacy_mode="off")
    assert data["can_start_simulation"] is True
    assert not data["blocking_errors"]
    assert any("dry-run" in str(w).lower() for w in data["warnings"])


def test_list_options_includes_types_from_all_industries(db):
    st = _survey_type(db)
    opts = SurveySimulatorService.list_options(db)
    ids = {t["id"] for t in opts["survey_types"]}
    assert st.id in ids
    assert opts["default_survey_type_id"] in ids
