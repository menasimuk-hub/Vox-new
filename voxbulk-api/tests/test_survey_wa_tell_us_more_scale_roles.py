"""Tell-us-more must trigger on feeling_word/helpfulness scales, not only numeric rating."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_runtime_service import (
    attach_builder_runtime_to_config,
    build_builder_runtime,
    runtime_tell_us_more_enabled,
    tell_us_more_blocks_vague_followup,
)
from app.services.survey_builder_flow_service import (
    is_low_answer_for_tell_us_more,
    is_tell_us_more_trigger_question,
    is_tell_us_more_trigger_role,
)
from app.services.survey_whatsapp_conversation_service import handle_inbound_reply


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
        components_json=json.dumps([{"type": "BODY", "text": body}]),
    )
    db.add(row)
    db.commit()
    return row


def test_runtime_enables_tell_us_more_for_feeling_word_only(db):
    welcome = _tpl(db, name="welcome", body="Hi", step_role="start")
    satisfaction = _tpl(
        db,
        name="job_sat",
        body="How content are you with your current role?",
        step_role="feeling_word",
    )
    tell = _tpl(db, name="tell_us_more", body="Sorry to hear that. What went wrong?", step_role="reason")
    thank = _tpl(db, name="thank", body="Thanks", step_role="completion")

    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="employee-experience",
        survey_type_name="Employee experience",
        privacy_mode="off",
        welcome_template_id=welcome.id,
        middle_template_ids=[satisfaction.id],
        tell_us_more_template_id=tell.id,
        thank_you_template_id=thank.id,
    )
    config = attach_builder_runtime_to_config({}, runtime)
    assert runtime_tell_us_more_enabled(config) is True
    branch = runtime["branches"]["tell_us_more_on_low_rating"]
    assert branch["enabled"] is True
    assert "feeling_word" in branch["from_step_roles"]


def test_is_low_answer_for_feeling_word_poor():
    question = {
        "step_role": "feeling_word",
        "options": ["Excellent", "Good", "Poor"],
    }
    assert is_tell_us_more_trigger_role("feeling_word") is True
    assert is_low_answer_for_tell_us_more("Poor", question=question) is True
    assert is_low_answer_for_tell_us_more("Excellent", question=question) is False


def test_step_snapshot_with_step_0_infers_rating_trigger():
    question = {
        "step_role": "step_0",
        "options": ["Excellent", "Good", "Poor"],
    }
    assert is_tell_us_more_trigger_question(question) is True
    assert is_tell_us_more_trigger_role("step_0") is False


def test_tell_us_more_blocks_vague_when_configured():
    config = {"tell_us_more_template_id": 42, "builder_runtime": {"tell_us_more_template_id": 42}}
    assert tell_us_more_blocks_vague_followup(config, {}) is True


@patch("app.services.survey_whatsapp_conversation_service._send_freeform_whatsapp")
@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_feeling_word_poor_triggers_tell_us_more_not_vague(mock_send, mock_freeform, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    mock_freeform.return_value = True

    org = Organisation(name="Employee Org")
    db.add(org)
    db.commit()

    welcome = _tpl(db, name="welcome", body="Hi {{1}}", step_role="start")
    satisfaction = _tpl(
        db,
        name="job_sat",
        body="How content are you with your current role?",
        step_role="feeling_word",
    )
    news = _tpl(
        db,
        name="news_clarity",
        body="How would you rate the clarity of company news?",
        step_role="feeling_word",
    )
    tell = _tpl(db, name="tell_us_more", body="Sorry to hear that. What went wrong?", step_role="reason")
    thank = _tpl(db, name="thank", body="Thanks", step_role="completion")

    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="employee-experience",
        survey_type_name="Employee experience",
        privacy_mode="off",
        welcome_template_id=welcome.id,
        middle_template_ids=[satisfaction.id, news.id],
        tell_us_more_template_id=tell.id,
        thank_you_template_id=thank.id,
    )
    config = attach_builder_runtime_to_config(
        {
            "delivery": "whatsapp",
            "survey_channel": "whatsapp",
            "channels": ["whatsapp"],
            "wa_template_id": welcome.id,
            "tell_us_more_template_id": tell.id,
        },
        runtime,
    )
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org.id,
        user_id="user-1",
        service_code="survey",
        title="Employee WA",
        status="running",
        payment_status="approved",
        config_json=json.dumps(config),
    )
    phone = "+447700900111"
    recipient = ServiceOrderRecipient(
        order_id=order.id,
        row_number=1,
        name="Qusay",
        phone=phone,
        status="in_progress",
        result_json=json.dumps(
            {
                "wa_conversation": {
                    "step": 1,
                    "total": 2,
                    "answers": [],
                    "started_at": datetime.utcnow().isoformat(),
                }
            }
        ),
    )
    db.add(order)
    db.add(recipient)
    db.commit()

    result = handle_inbound_reply(db, from_phone=phone, body="Poor", org_id=org.id)

    assert result.get("handled") is True
    assert result.get("payload_source") == "builder_tell_us_more_template"
    assert result.get("vague_followup") is not True
    assert mock_freeform.called
    freeform_body = str(mock_freeform.call_args.kwargs.get("body") or "")
    assert "sorry" in freeform_body.lower() or "wrong" in freeform_body.lower()
    assert "what was wrong with" not in freeform_body.lower()
