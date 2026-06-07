"""Tests for auto vague-negative WhatsApp survey follow-up."""

from __future__ import annotations

import json

import pytest

from app.services.survey_wa_vague_negative_followup_service import (
    attach_auto_followup_to_template_item,
    build_auto_followup_metadata,
    generate_followup_text,
    is_whatsapp_service_window_open,
    normalize_template_example_values,
    should_ask_vague_negative_followup,
)


class _SurveyType:
    slug = "food_quality"
    name = "Food quality"


def test_normalize_template_example_values_no_variables():
    item = {"header": "", "body": "How was the food quality on your visit?", "example_values": ["Sample"]}
    out = normalize_template_example_values(item)
    assert out["example_values"] == []


def test_normalize_template_example_values_with_variables():
    item = {"header": "", "body": "Hi {{1}}, thanks for visiting {{2}}.", "example_values": ["Sample", "Sample"]}
    out = normalize_template_example_values(item)
    assert out["example_values"] == ["Alex", "Northgate Dental"]
    assert "Sample" not in out["example_values"]


def test_build_auto_followup_metadata_food_quality():
    meta = build_auto_followup_metadata(
        survey_type=_SurveyType(),
        industry_slug="hospitality_food",
        step_role="rating",
        question_text="How was the food quality on your visit?",
    )
    assert meta["auto_followup_enabled"] is True
    assert meta["followup_mode"] == "auto_vague_negative"
    assert meta["question_topic"] == "food_quality"
    assert meta["answer_kind"] == "rating"
    assert meta["followup_profile"] == "quality_issue"


def test_attach_auto_followup_sets_outcome_variables():
    class DeliveryType:
        slug = "delivery_experience"
        name = "Delivery experience"

    item = attach_auto_followup_to_template_item(
        {"body": "How was the delivery?", "step_role": "rating"},
        survey_type=DeliveryType(),
        industry_slug="logistics",
    )
    assert "auto_followup" in item
    assert item["outcome_variables"]["auto_followup"]["question_topic"] == "delivery"


@pytest.mark.parametrize(
    "answer,expect_followup",
    [
        ("Bad", True),
        ("Poor", True),
        ("1", True),
        ("2 stars", True),
        ("price too high", False),
        ("Too expensive", False),
        ("Delivery was late", False),
        ("Support never replied", False),
    ],
)
def test_should_ask_vague_negative_followup_cases(answer, expect_followup):
    question = {
        "step_role": "rating",
        "text": "How was the food quality on your visit?",
        "auto_followup": build_auto_followup_metadata(
            survey_type=_SurveyType(),
            step_role="rating",
            question_text="How was the food quality on your visit?",
        ),
    }
    assert (
        should_ask_vague_negative_followup(answer=answer, question=question, config={})
        is expect_followup
    )


def test_should_ask_followup_without_metadata_uses_heuristics():
    question = {"step_role": "rating", "text": "How would you rate our service?"}
    assert should_ask_vague_negative_followup(answer="bad", question=question, config={}) is True
    assert should_ask_vague_negative_followup(answer="price too high", question=question, config={}) is False


def test_generate_followup_text_uses_question_topic():
    question = {
        "text": "How was the food quality on your visit?",
        "auto_followup": {"question_topic": "food_quality", "followup_profile": "quality_issue"},
    }
    text = generate_followup_text(question=question)
    assert "food quality" in text.lower() or "sorry" in text.lower()


def test_service_window_open_with_recent_inbound(db):
    from app.models.whatsapp_log import WhatsAppLog
    from datetime import datetime

    row = WhatsAppLog(
        org_id="org-1",
        provider="telnyx",
        direction="inbound",
        from_number="+447954823445",
        to_number="+441234567890",
        body="Bad",
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    assert is_whatsapp_service_window_open(
        db,
        org_id="org-1",
        recipient_phone="+447954823445",
        log_id=row.id,
    )


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
