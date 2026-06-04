"""DELETE survey type template (unlink from step bank)."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_type_template_service import SurveyTypeTemplateService, SurveyTypeTemplateError
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService


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
        yield session
    finally:
        session.close()


def _survey_type(db) -> SurveyType:
    row = db.execute(select(SurveyType).limit(1)).scalar_one()
    return row


def test_unlink_template_from_survey_type(db):
    st = _survey_type(db)
    tpl = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=st)

    result = SurveyTypeTemplateService.unlink_template_from_survey_type(
        db, survey_type_id=st.id, template_id=tpl.id
    )
    assert result["ok"] is True
    remaining = db.execute(
        select(SurveyTypeTemplate).where(
            SurveyTypeTemplate.survey_type_id == st.id,
            SurveyTypeTemplate.template_id == tpl.id,
        )
    ).scalar_one_or_none()
    assert remaining is None


def test_unlink_with_mapping_industry_mismatch_row_industry(db):
    """List shows templates when mapping industry matches; delete must use mapping too."""
    st = _survey_type(db)
    other = db.execute(select(SurveyType).where(SurveyType.id != st.id).limit(1)).scalar_one()
    now = datetime.utcnow()
    tpl = SurveyWhatsappTemplateService.create_standard_draft(db, survey_type=st)
    tpl.industry_id = other.industry_id
    db.add(tpl)
    mapping = db.execute(
        select(SurveyTypeTemplate).where(
            SurveyTypeTemplate.survey_type_id == st.id,
            SurveyTypeTemplate.template_id == tpl.id,
        )
    ).scalar_one()
    mapping.industry_id = st.industry_id
    db.add(mapping)
    db.commit()

    result = SurveyTypeTemplateService.unlink_template_from_survey_type(
        db, survey_type_id=st.id, template_id=tpl.id
    )
    assert result["ok"] is True


def test_unlink_fails_when_not_linked(db):
    st = _survey_type(db)
    now = datetime.utcnow()
    local_id = f"local-{uuid.uuid4().hex}"
    tpl = TelnyxWhatsappTemplate(
        telnyx_record_id=local_id,
        template_id=local_id,
        name=f"voxbulk_survey_{st.slug}_orphan",
        language="en_US",
        category="MARKETING",
        status="LOCAL_DRAFT",
        survey_type_id=st.id,
        active_for_survey=True,
        created_at=now,
        updated_at=now,
    )
    db.add(tpl)
    db.commit()
    with pytest.raises(SurveyTypeTemplateError, match="not linked"):
        SurveyTypeTemplateService.unlink_template_from_survey_type(
            db, survey_type_id=st.id, template_id=tpl.id
        )
