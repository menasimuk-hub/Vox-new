"""WA Survey internal simulator and test pack seed."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_wa_test_pack_seed_service import (
    TEST_SURVEY_TYPE_SLUG,
    SurveyWaTestPackSeedService,
)
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
        yield session
    finally:
        session.close()


def test_ensure_test_pack_creates_twelve_templates(db):
    result = SurveyWaTestPackSeedService.ensure_test_pack(db)
    assert result["template_count"] == 12
    assert result["survey_type"]["slug"] == TEST_SURVEY_TYPE_SLUG
    outcomes = (
        db.query(TelnyxWhatsappTemplate)
        .filter(
            TelnyxWhatsappTemplate.survey_type_id == result["survey_type"]["id"],
            TelnyxWhatsappTemplate.step_role == "completion",
        )
        .all()
    )
    assert len(outcomes) == 3
    assert {r.outcome_key for r in outcomes} == {"happy", "neutral", "unhappy"}


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_simulator_graph_low_rating_unhappy(mock_send, db):
    mock_send.return_value = type("R", (), {"ok": True, "detail": "ok", "channel": "whatsapp"})()
    pack = SurveyWaTestPackSeedService.ensure_test_pack(db)
    st_id = pack["survey_type"]["id"]
    started = SurveySimulatorService.start(
        db,
        survey_type_id=st_id,
        privacy_mode="off",
        flow_engine="graph",
        page_count=6,
        selected_step_roles=["start", "rating", "yes_no", "helpfulness", "reason", "completion"],
    )
    state = started["state"]
    assert state["completed"] is False
    assert state["awaiting_start"] is True
    assert state["current_step_role"] == "start"

    state = SurveySimulatorService.answer(db, recipient_id=state["recipient_id"], answer="Start survey")["state"]
    assert state["completed"] is False
    assert state["current_step_role"] == "rating"

    # Low rating on first graph node triggers unhappy outcome
    done = SurveySimulatorService.answer(db, recipient_id=state["recipient_id"], answer="1")["state"]
    assert done["completed"] is True
    assert done["outcome_key"] == "unhappy"
    assert done["outcome_delivery"].get("ok") is True


def test_simulator_live_test_rejects_invalid_phone(db):
    pack = SurveyWaTestPackSeedService.ensure_test_pack(db)
    st_id = pack["survey_type"]["id"]
    with pytest.raises(ValueError, match="E.164"):
        SurveySimulatorService.start(
            db,
            survey_type_id=st_id,
            test_phone="not-a-phone",
            skip_test_pack_seed=True,
        )
