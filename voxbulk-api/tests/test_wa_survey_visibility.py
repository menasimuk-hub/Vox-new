"""Tests for WA Survey customer catalog visibility."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import inspect, text

from app.core.database import Base, get_engine, get_sessionmaker
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.wa_survey_visibility_service import (
    list_wa_survey_customer_catalog_types,
    set_wa_survey_type_active,
)


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    insp = inspect(engine)
    if "survey_types" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("survey_types")}
        if "wa_platform_block_exempt" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE survey_types "
                        "ADD COLUMN wa_platform_block_exempt BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
        cols = {c["name"] for c in insp.get_columns("survey_types")}
        if "customer_hidden" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE survey_types "
                        "ADD COLUMN customer_hidden BOOLEAN NOT NULL DEFAULT 0"
                    )
                )


def test_wa_survey_catalog_excludes_disabled_type():
    with get_sessionmaker()() as db:
        industry = Industry(
            id=str(uuid.uuid4()),
            slug=f"wa-ind-{uuid.uuid4().hex[:6]}",
            name="WA Industry",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(industry)
        db.flush()
        active_type = SurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="team_collaboration",
            name="Team collaboration",
            is_active=True,
            customer_hidden=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        disabled_type = SurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="disabled_topic",
            name="Disabled topic",
            is_active=False,
            customer_hidden=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add_all([active_type, disabled_type])
        db.flush()
        tpl = TelnyxWhatsappTemplate(
            telnyx_record_id=f"rec-{uuid.uuid4().hex[:8]}",
            template_id=f"tpl-{uuid.uuid4().hex[:8]}",
            name="voxbulk_survey_team_collaboration_test_abc",
            language="en_GB",
            category="utility",
            status="APPROVED",
            survey_type_id=active_type.id,
            active_for_survey=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(tpl)
        db.flush()
        db.add(
            SurveyTypeTemplate(
                industry_id=industry.id,
                survey_type_id=active_type.id,
                template_id=tpl.id,
                usable_as_standard=True,
                is_default_standard=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        db.commit()

        items = list_wa_survey_customer_catalog_types(db, industry_id=industry.id)
        ids = {item["id"] for item in items}
        assert active_type.id in ids
        assert disabled_type.id not in ids


def test_set_wa_survey_type_active_sets_customer_hidden():
    with get_sessionmaker()() as db:
        industry = Industry(
            id=str(uuid.uuid4()),
            slug=f"toggle-{uuid.uuid4().hex[:6]}",
            name="Toggle Industry",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(industry)
        db.flush()
        survey_type = SurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
            slug="toggle_topic",
            name="Toggle topic",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(survey_type)
        db.commit()

        set_wa_survey_type_active(db, survey_type.id, active=False)
        db.refresh(survey_type)
        assert survey_type.is_active is False
        assert survey_type.customer_hidden is True

        set_wa_survey_type_active(db, survey_type.id, active=True)
        db.refresh(survey_type)
        assert survey_type.is_active is True
        assert survey_type.customer_hidden is False
