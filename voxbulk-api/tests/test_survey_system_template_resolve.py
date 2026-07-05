"""System template resolution must survive duplicate SurveyType rows per kind."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_runtime_service import (
    attach_builder_runtime_to_config,
    build_builder_runtime,
    hydrate_missing_tell_us_more_on_config,
    runtime_tell_us_more_enabled,
    tell_us_more_blocks_vague_followup,
)
from app.services.survey_system_template_service import SurveySystemTemplateService


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
        SurveySystemTemplateService.ensure_system_survey_types(session)
        yield session
    finally:
        session.close()


def _duplicate_tell_us_more_types(db):
    """Simulate production: two SurveyType rows with system_template_kind=tell_us_more."""
    industry = SurveySystemTemplateService.ensure_system_industry(db)
    now = datetime.utcnow()
    empty = SurveyType(
        id=str(uuid.uuid4()),
        industry_id=industry.id,
        slug="tell_us_more_dup_empty",
        name="Tell us more empty dup",
        is_active=True,
        default_length="standard",
        min_length=4,
        max_length=6,
        supports_anonymous=True,
        system_template_kind="tell_us_more",
        sort_order=200,
        created_at=now,
        updated_at=now,
    )
    db.add(empty)
    db.flush()

    st_ids = list(
        db.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(SurveyType.id).where(
                SurveyType.system_template_kind == "tell_us_more",
                SurveyType.slug == "tell_us_more",
            )
        ).scalars()
    )
    assert st_ids, "canonical tell_us_more SurveyType missing"
    canonical_id = st_ids[0]

    tpl = TelnyxWhatsappTemplate(
        telnyx_record_id=f"local-{uuid.uuid4().hex}",
        template_id=f"local-{uuid.uuid4().hex}",
        name="voxbulk_survey_tell_us_more_test",
        display_name="Tell us more template",
        language="en_US",
        category="UTILITY",
        status="APPROVED",
        step_role="reason",
        body_preview="Sorry to hear that. What went wrong?",
        active_for_survey=True,
        variant_type="standard",
        privacy_mode="off",
        sync_from_meta=False,
        components_json=json.dumps([{"type": "BODY", "text": "Sorry to hear that. What went wrong?"}]),
        created_at=now,
        updated_at=now,
    )
    db.add(tpl)
    db.flush()
    db.add(
        SurveyTypeTemplate(
            survey_type_id=canonical_id,
            template_id=tpl.id,
            industry_id=industry.id,
        )
    )
    db.commit()
    return empty, canonical_id, tpl


def test_resolve_tell_us_more_finds_template_with_duplicate_survey_types(db):
    _duplicate_tell_us_more_types(db)
    tid = SurveySystemTemplateService.resolve_tell_us_more_template_id(db, {"anonymous_responses": False})
    assert tid is not None


def test_hydrate_repairs_order_missing_tell_us_more(db):
    _duplicate_tell_us_more_types(db)
    welcome = db.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(TelnyxWhatsappTemplate).limit(1)
    ).scalar_one_or_none()

    feeling = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="feeling_step",
        display_name="Balance",
        language="en_US",
        category="MARKETING",
        body_preview="Rate balance",
        step_role="feeling_word",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json="[]",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(feeling)
    db.commit()

    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="employee-experience",
        survey_type_name="Employee",
        privacy_mode="off",
        welcome_template_id=welcome.id if welcome else feeling.id,
        middle_template_ids=[feeling.id],
        tell_us_more_template_id=None,
        thank_you_template_id=welcome.id if welcome else feeling.id,
    )
    broken = attach_builder_runtime_to_config({"anonymous_responses": False}, runtime)
    assert broken.get("tell_us_more_template_id") is None
    assert runtime_tell_us_more_enabled(broken) is False

    repaired = hydrate_missing_tell_us_more_on_config(db, broken)
    assert repaired.get("tell_us_more_template_id") is not None
    assert runtime_tell_us_more_enabled(repaired) is True
    assert tell_us_more_blocks_vague_followup(repaired, {}) is True
