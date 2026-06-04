"""Simulator deep-link prefill from saved survey type templates."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_flow_constants import FLOW_ENGINE_LINEAR
from app.services.survey_simulator_service import SurveySimulatorService


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
