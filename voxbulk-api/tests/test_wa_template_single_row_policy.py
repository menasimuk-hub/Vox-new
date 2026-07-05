"""Tests for single-row template policy and conditional pending sync."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import Base, get_engine, get_sessionmaker
import app.models  # noqa: F401
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_system_template_service import SurveySystemTemplateService
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_wa_template_clone_push_service import maybe_clone_and_push_on_meta_error
from app.services.survey_wa_template_supersede_service import (
    has_pending_survey_templates,
    sync_pending_wa_templates_if_any,
)
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    survey_template_to_dict,
)


@pytest.fixture()
def db():
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


def test_maybe_clone_and_push_never_creates_row(db):
    row = TelnyxWhatsappTemplate(
        telnyx_record_id="local_test_no_clone",
        template_id=str(uuid.uuid4()),
        name="voxbulk_survey_test_no_clone",
        language="en_US",
        category="UTILITY",
        status="APPROVED",
        active_for_survey=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    before = db.execute(select(TelnyxWhatsappTemplate)).scalars().all()
    exc = SurveyWhatsappTemplateError(
        "blocked",
        payload={"requires_draft_reset_or_clone": True},
    )
    assert maybe_clone_and_push_on_meta_error(db, row, exc) is None
    after = db.execute(select(TelnyxWhatsappTemplate)).scalars().all()
    assert len(after) == len(before)


def test_has_pending_survey_templates_detects_pending(db):
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="voxbulk_survey_pending_detect",
        language="en_US",
        category="UTILITY",
        status="PENDING",
        active_for_survey=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    assert has_pending_survey_templates(db) is True


def test_sync_pending_skips_when_none_pending(db):
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="voxbulk_survey_approved_only",
        language="en_US",
        category="UTILITY",
        status="APPROVED",
        active_for_survey=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    result = sync_pending_wa_templates_if_any(db)
    assert result.get("skipped") is True


def test_survey_template_to_dict_prefers_draft_body(db):
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="voxbulk_survey_thank_body",
        language="en_US",
        category="UTILITY",
        status="APPROVED",
        step_role="completion",
        active_for_survey=True,
        body_preview="Old stale preview text",
        draft_components_json='[{"type": "BODY", "text": "Fresh draft thank you body"}]',
        components_json='[{"type": "BODY", "text": "Old remote body"}]',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    payload = survey_template_to_dict(row)
    assert payload["body_preview"] == "Fresh draft thank you body"
