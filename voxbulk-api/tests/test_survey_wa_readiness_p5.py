"""P5: WA Survey readiness and outcome matrix APIs."""

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
from app.services.survey_wa_readiness_service import SurveyWaReadinessService
from app.services.survey_industry_scope import apply_industry_to_template
from app.services.survey_outcome_template_service import default_outcome_variables
from app.services.wa_template_privacy import PRIVACY_MODE_OFF


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
        slug=f"readiness-{uuid.uuid4().hex[:6]}",
        name="Readiness Test",
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


def _completion_tpl(db, *, survey_type: SurveyType, outcome_key: str, approved: bool = True):
    tid = f"local-{uuid.uuid4().hex}"
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=tid,
        template_id=tid,
        name=f"test_{outcome_key}",
        display_name=f"Test {outcome_key}",
        language="en_US",
        category="UTILITY",
        status="APPROVED" if approved else "PENDING",
        step_role="completion",
        outcome_key=outcome_key,
        privacy_mode=PRIVACY_MODE_OFF,
        variant_type="standard",
        survey_type_id=survey_type.id,
        industry_id=survey_type.industry_id,
        active_for_survey=True,
        body_preview=f"Thanks {{1}}",
        components_json=json.dumps([{"type": "BODY", "text": "Thanks {{1}}"}]),
        outcome_variables_json=json.dumps(default_outcome_variables(outcome_key)),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        synced_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    apply_industry_to_template(row, survey_type)
    db.commit()
    return row


def test_outcome_matrix_shows_happy_neutral_unhappy(db):
    st = _survey_type(db)
    _completion_tpl(db, survey_type=st, outcome_key="happy")
    _completion_tpl(db, survey_type=st, outcome_key="neutral", approved=False)

    matrix = SurveyWaReadinessService.build_outcome_matrix(db, survey_type=st, privacy_mode="off")
    keys = {r["outcome_key"] for r in matrix}
    assert keys == {"happy", "neutral", "unhappy"}
    happy = next(r for r in matrix if r["outcome_key"] == "happy")
    assert happy["approved"] is True
    assert happy["action_type"] == "send_template"
    unhappy = next(r for r in matrix if r["outcome_key"] == "unhappy")
    assert unhappy["template_id"] is None
    assert unhappy["will_text_fallback"] is True


def test_readiness_reports_missing_start_and_flow_warning(db):
    st = _survey_type(db)
    result = SurveyWaReadinessService.readiness(db, survey_type_id=st.id, privacy_mode="off")
    assert result["ok"] is False
    assert any("start template" in e.lower() for e in result["errors"])
    assert any("published default graph" in w.lower() for w in result["warnings"])
    assert len(result["outcome_matrix"]) == 3
