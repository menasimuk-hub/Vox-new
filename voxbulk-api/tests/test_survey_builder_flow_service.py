"""Tests for strict builder step sequence (template-id order, no step-bank fallback)."""

from __future__ import annotations

import uuid

import pytest

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_flow_service import build_builder_step_sequence
from app.services.survey_step_bank_service import STEP_REPLY_CONFIG


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


def _tpl(db, *, name: str, body: str, step_role: str) -> TelnyxWhatsappTemplate:
    record_id = str(uuid.uuid4())
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=record_id,
        template_id=record_id,
        name=name,
        display_name=name,
        language="en_US",
        category="MARKETING",
        body_preview=body,
        step_role=step_role,
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json='[{"type":"BODY","text":"' + body.replace('"', '\\"') + '"}]',
    )
    db.add(row)
    db.commit()
    return row


def test_builder_step_sequence_uses_exact_template_rows_not_step_bank(db):
    hospitality = _tpl(
        db,
        name="voxbulk_hospitality_value",
        body="How would you rate the value for money of your food and drink?",
        step_role="abc_choice",
    )
    legacy_helpfulness = _tpl(
        db,
        name="voxbulk_legacy_helpfulness",
        body="Thanks, {{1}}. Thinking about your appointment at {{2}}, how helpful was the team?",
        step_role="helpfulness",
    )
    steps = build_builder_step_sequence(
        db,
        middle_template_ids=[hospitality.id],
        business_name="Cafe Live",
        first_name="Alex",
    )
    assert len(steps) == 1
    assert steps[0]["template_id"] == hospitality.id
    assert "value for money" in steps[0]["text"].lower()
    assert steps[0]["options"] != STEP_REPLY_CONFIG["helpfulness"]["options"]
    assert legacy_helpfulness.id not in [s["template_id"] for s in steps]
