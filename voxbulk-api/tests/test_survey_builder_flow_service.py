"""Tests for strict builder step sequence (template-id order, no step-bank fallback)."""

from __future__ import annotations

import uuid

import pytest

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_flow_service import (
    SurveyBuilderFlowError,
    assert_builder_template_allowed,
    build_builder_step_sequence,
    effective_order_config,
    is_builder_bound_flow,
    sanitize_builder_config,
)
from app.services.survey_flow_config_service import is_graph_flow
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


def test_sanitize_builder_config_strips_stale_graph(db):
    hospitality = _tpl(
        db,
        name="voxbulk_hospitality_rating",
        body="Rate your meal from 0 to 10.",
        step_role="rating",
    )
    seq = build_builder_step_sequence(db, middle_template_ids=[hospitality.id])
    raw = {
        "flow_engine": "graph",
        "flow_snapshot": {"nodes": {"abc": {"step_role": "abc_choice", "question": {"text": "legacy"}}}},
        "flow_snapshot_json": '{"nodes":{"abc":{}}}',
        "builder_step_sequence": seq,
        "builder_template_ids": [hospitality.id],
        "whatsapp_flow": {"questions": seq},
    }
    cleaned = effective_order_config(raw)
    assert is_builder_bound_flow(cleaned)
    assert cleaned.get("flow_snapshot") is None
    assert cleaned.get("flow_snapshot_json") is None
    assert cleaned["flow_engine"] == "linear"
    assert is_graph_flow(cleaned) is False


def test_assert_builder_template_allowed_hard_fails(db):
    allowed = _tpl(db, name="allowed_tpl", body="Allowed question?", step_role="yes_no")
    config = {
        "builder_step_sequence": [{"template_id": allowed.id, "step_role": "yes_no", "text": "Allowed?"}],
        "builder_template_ids": [allowed.id],
    }
    assert assert_builder_template_allowed(config, allowed.id, context="test") == allowed.id
    with pytest.raises(SurveyBuilderFlowError, match="builder flow violation"):
        assert_builder_template_allowed(config, 99999, context="test")


def test_rating_answer_is_low_accepts_poor_button_label():
    from app.services.survey_builder_flow_service import _rating_answer_is_low

    question = {"options": ["Excellent", "Good", "Poor"], "step_role": "rating"}
    assert _rating_answer_is_low("Poor", question=question) is True
    assert _rating_answer_is_low("Excellent", question=question) is False
    assert _rating_answer_is_low("8", question=question) is False


def test_is_low_answer_for_tell_us_more_feeling_word_and_yes_no():
    from app.services.survey_builder_flow_service import is_low_answer_for_tell_us_more

    feeling = {
        "step_role": "feeling_word",
        "options": ["Excellent", "Good", "Poor"],
    }
    assert is_low_answer_for_tell_us_more("Poor", question=feeling) is True
    assert is_low_answer_for_tell_us_more("Excellent", question=feeling) is False

    yes_no = {"step_role": "yes_no", "options": ["Yes", "No"]}
    assert is_low_answer_for_tell_us_more("No", question=yes_no) is True
    assert is_low_answer_for_tell_us_more("Yes", question=yes_no) is False

    good_bad = {"step_role": "step_0", "options": ["Good", "Bad"]}
    assert is_low_answer_for_tell_us_more("Bad", question=good_bad) is True
    assert is_low_answer_for_tell_us_more("Good", question=good_bad) is False


def test_order_scale_labels_puts_worst_last():
    from app.services.survey_wa_flow_constants import order_scale_labels

    assert order_scale_labels(["Poor", "Good", "Excellent"], step_role="rating") == [
        "Excellent",
        "Good",
        "Poor",
    ]
    assert order_scale_labels(["Low", "Moderate", "High"], step_role="rating") == [
        "High",
        "Moderate",
        "Low",
    ]
