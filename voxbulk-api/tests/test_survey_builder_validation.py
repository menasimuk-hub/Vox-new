"""Survey builder validation — service tags and system templates."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_validation_service import (
    SurveyBuilderValidationError,
    SurveyBuilderValidationService,
)
from app.services.survey_system_template_service import SurveySystemTemplateService
from app.services.survey_type_service import SurveyTypeService


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
        SurveyTypeService.ensure_defaults(session)
        SurveySystemTemplateService.ensure_system_survey_types(session)
        yield session
    finally:
        session.close()


def _regular_type(db) -> tuple[Industry, SurveyType]:
    IndustryService.ensure_defaults(db)
    industry = IndustryService.get_by_slug(db, "general")
    assert industry is not None
    st = db.execute(select(SurveyType).where(SurveyType.industry_id == industry.id).limit(1)).scalar_one()
    return industry, st


def test_clamp_template_count():
    assert SurveyBuilderValidationService.clamp_template_count(0) == 1
    assert SurveyBuilderValidationService.clamp_template_count(5) == 5
    assert SurveyBuilderValidationService.clamp_template_count(99) == 50


def test_validate_requires_service_tags(db):
    industry, st = _regular_type(db)
    with pytest.raises(SurveyBuilderValidationError):
        SurveyBuilderValidationService.validate_builder_selection(
            db,
            industry_id=industry.id,
            selected_survey_type_ids=[],
            welcome_template_id=None,
            thank_you_template_id=None,
        )


def test_validate_requires_wa_template_on_tag(db):
    industry, st = _regular_type(db)
    with pytest.raises(SurveyBuilderValidationError, match="no WhatsApp template"):
        SurveyBuilderValidationService.validate_builder_selection(
            db,
            industry_id=industry.id,
            selected_survey_type_ids=[st.id],
            welcome_template_id=1,
            thank_you_template_id=1,
        )


def test_validate_ok_with_templates(db):
    industry, st = _regular_type(db)
    now = datetime.utcnow()
    local_id = f"local-{uuid.uuid4().hex}"
    tpl = TelnyxWhatsappTemplate(
        telnyx_record_id=local_id,
        template_id=local_id,
        name=f"voxbulk_survey_{st.slug}_start",
        language="en_US",
        category="MARKETING",
        status="APPROVED",
        survey_type_id=st.id,
        industry_id=industry.id,
        active_for_survey=True,
        created_at=now,
        updated_at=now,
    )
    db.add(tpl)
    db.flush()
    db.add(SurveyTypeTemplate(survey_type_id=st.id, template_id=tpl.id, industry_id=industry.id))
    middle_tpl = TelnyxWhatsappTemplate(
        telnyx_record_id=f"local-{uuid.uuid4().hex}",
        template_id=f"local-{uuid.uuid4().hex}",
        name=f"voxbulk_survey_{st.slug}_rating",
        language="en_US",
        category="MARKETING",
        status="APPROVED",
        survey_type_id=st.id,
        industry_id=industry.id,
        step_role="rating",
        active_for_survey=True,
        created_at=now,
        updated_at=now,
    )
    db.add(middle_tpl)
    db.flush()
    db.add(
        SurveyTypeTemplate(survey_type_id=st.id, template_id=middle_tpl.id, industry_id=industry.id)
    )
    welcome_types = db.execute(
        select(SurveyType).where(SurveyType.system_template_kind == "welcome")
    ).scalars().all()
    thank_types = db.execute(
        select(SurveyType).where(SurveyType.system_template_kind == "thank_you")
    ).scalars().all()
    tell_types = db.execute(
        select(SurveyType).where(SurveyType.system_template_kind == "tell_us_more")
    ).scalars().all()
    welcome_tpl = TelnyxWhatsappTemplate(
        telnyx_record_id=f"local-{uuid.uuid4().hex}",
        template_id=f"local-{uuid.uuid4().hex}",
        name="voxbulk_survey_welcome_a",
        language="en_US",
        category="MARKETING",
        status="APPROVED",
        survey_type_id=welcome_types[0].id,
        active_for_survey=True,
        created_at=now,
        updated_at=now,
    )
    thank_tpl = TelnyxWhatsappTemplate(
        telnyx_record_id=f"local-{uuid.uuid4().hex}",
        template_id=f"local-{uuid.uuid4().hex}",
        name="voxbulk_survey_thank_a",
        language="en_US",
        category="MARKETING",
        status="APPROVED",
        survey_type_id=thank_types[0].id,
        active_for_survey=True,
        created_at=now,
        updated_at=now,
    )
    tell_tpl = TelnyxWhatsappTemplate(
        telnyx_record_id=f"local-{uuid.uuid4().hex}",
        template_id=f"local-{uuid.uuid4().hex}",
        name="voxbulk_survey_tell_more",
        language="en_US",
        category="MARKETING",
        status="APPROVED",
        survey_type_id=tell_types[0].id,
        active_for_survey=True,
        created_at=now,
        updated_at=now,
    )
    db.add_all([welcome_tpl, thank_tpl, tell_tpl])
    db.flush()
    db.add(
        SurveyTypeTemplate(
            survey_type_id=welcome_types[0].id,
            template_id=welcome_tpl.id,
            industry_id=welcome_types[0].industry_id,
        )
    )
    db.add(
        SurveyTypeTemplate(
            survey_type_id=thank_types[0].id,
            template_id=thank_tpl.id,
            industry_id=thank_types[0].industry_id,
        )
    )
    db.add(
        SurveyTypeTemplate(
            survey_type_id=tell_types[0].id,
            template_id=tell_tpl.id,
            industry_id=tell_types[0].industry_id,
        )
    )
    db.commit()

    result = SurveyBuilderValidationService.validate_builder_selection(
        db,
        industry_id=industry.id,
        selected_survey_type_ids=[st.id],
        welcome_template_id=welcome_tpl.id,
        thank_you_template_id=thank_tpl.id,
        selected_service_template_ids={st.id: middle_tpl.id},
        require_approved=True,
    )
    assert result["ok"] is True
    assert result["tell_us_more_template_id"] == tell_tpl.id
