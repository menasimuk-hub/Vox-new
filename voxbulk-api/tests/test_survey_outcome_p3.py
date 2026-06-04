"""P3: outcome completion templates and WhatsApp outcome delivery."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_flow_compiler_service import compile_linear_graph
from app.services.survey_flow_config_service import attach_flow_to_config
from app.services.survey_outcome_template_service import (
    SurveyOutcomeTemplateService,
    build_variable_context,
)
from app.services.survey_outcome_send_service import SurveyOutcomeSendService
from app.services.survey_session_service import SurveySessionService
from app.services.survey_whatsapp_conversation_service import handle_inbound_reply, send_first_question
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
    industry = IndustryService.list_industries(db, active_only=True)[0]
    st = SurveyType(
        id=str(uuid.uuid4()),
        industry_id=industry["id"] if isinstance(industry, dict) else industry.id,
        slug="test_csat",
        name="Test CSAT",
        is_active=True,
    )
    db.add(st)
    db.commit()
    return st


def _completion_template(
    db,
    *,
    survey_type: SurveyType,
    outcome_key: str,
    status: str = "APPROVED",
) -> TelnyxWhatsappTemplate:
    from app.services.survey_industry_scope import apply_industry_to_template
    from app.services.survey_outcome_template_service import default_outcome_variables

    tid = f"local-{uuid.uuid4().hex}"
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=tid,
        template_id=tid,
        name=f"pack_{survey_type.slug}_{outcome_key}",
        display_name=f"Close {outcome_key}",
        step_role="completion",
        outcome_key=outcome_key,
        outcome_variables_json=json.dumps(default_outcome_variables(outcome_key)),
        language="en_US",
        category="UTILITY",
        status=status,
        variant_type="standard",
        privacy_mode=PRIVACY_MODE_OFF,
        survey_type_id=survey_type.id,
        industry_id=survey_type.industry_id,
        body_preview=f"Thanks {{1}} from {{2}} — {outcome_key}",
        components_json=json.dumps(
            [{"type": "BODY", "text": f"Thanks {{{{1}}}} from {{{{2}}}} — {outcome_key}"}]
        ),
        active_for_survey=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        synced_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    apply_industry_to_template(row, survey_type)
    db.commit()
    return row


def test_enrich_snapshot_uses_approved_template(db):
    st = _survey_type(db)
    for ok in ("happy", "neutral", "unhappy"):
        _completion_template(db, survey_type=st, outcome_key=ok)
    snap = compile_linear_graph(
        page_roles=["start", "rating", "yes_no", "completion"],
        questions=[
            {"step_role": "rating", "text": "Rate", "reply_type": "rating", "options": ["1", "2", "3"]},
        ],
        max_question_visits=4,
        closing_body="Thanks",
    )
    enriched = SurveyOutcomeTemplateService.enrich_snapshot_outcomes(
        db,
        snapshot=snap,
        survey_type=st,
        privacy_mode=PRIVACY_MODE_OFF,
        context=build_variable_context(first_name="Sam", org_name="Acme", organiser="Team"),
    )
    unhappy = next(o for o in enriched["outcomes"] if o["outcome_key"] == "unhappy")
    assert unhappy["action_type"] == "send_template"
    assert unhappy.get("template_send")
    assert unhappy["template_send"]["template_id"]


@patch("app.services.survey_outcome_send_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_survey_message")
def test_graph_outcome_uses_whatsapp_template_send(mock_survey_msg, mock_wa, db):
    mock_survey_msg.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    mock_wa.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="tpl", external_id="x1")

    st = _survey_type(db)
    for ok in ("happy", "neutral", "unhappy"):
        _completion_template(db, survey_type=st, outcome_key=ok)

    page_roles = ["start", "rating", "yes_no", "completion"]
    questions = [
        {"step_role": "rating", "text": "Rate", "reply_type": "rating", "options": ["1", "2", "3", "4", "5"]},
        {"step_role": "yes_no", "text": "OK?", "reply_type": "true_false", "options": ["Yes", "No"]},
    ]
    snap = compile_linear_graph(
        page_roles=page_roles,
        questions=questions,
        max_question_visits=5,
        closing_body="Thanks",
        branches=[
            {
                "from_step_role": "rating",
                "to_step_role": "unhappy",
                "priority": 5,
                "rule_key": "branch.low",
                "condition": {
                    "op": "lte",
                    "source": "last_answer.normalized_value",
                    "value": "2",
                    "cast": "int",
                },
            },
        ],
    )
    enriched = SurveyOutcomeTemplateService.enrich_snapshot_outcomes(
        db,
        snapshot=snap,
        survey_type=st,
        privacy_mode=PRIVACY_MODE_OFF,
        context=build_variable_context(first_name="Jane", org_name="Acme", organiser="Sam"),
    )
    config = attach_flow_to_config(
        {
            "survey_channel": "whatsapp",
            "channels": ["whatsapp"],
            "survey_type_id": st.id,
            "page_roles": page_roles,
            "page_count": 5,
            "whatsapp_flow": {"questions": questions, "page_roles": page_roles},
        },
        snapshot=enriched,
        flow_definition_id=None,
    )
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="Outcome P3",
        status="running",
        payment_status="approved",
        recipient_count=1,
        quote_total_pence=2900,
        config_json=json.dumps(config),
        run_mode="scheduled",
        scheduled_start_at=datetime.utcnow() - timedelta(hours=1),
        scheduled_end_at=datetime.utcnow() + timedelta(hours=2),
        started_at=datetime.utcnow(),
    )
    db.add(order)
    db.commit()
    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        name="Jane",
        phone="+447700900123",
        status="sent",
    )
    db.add(recipient)
    db.commit()

    send_first_question(db, order=order, recipient=recipient, config=config)
    handle_inbound_reply(db, from_phone="+447700900123", body="1")

    assert mock_wa.called
    session = SurveySessionService.get_by_recipient(db, recipient.id)
    assert session.outcome_key == "unhappy"
    delivery = json.loads(session.outcome_delivery_json or "{}")
    assert delivery.get("sent_at")
    assert SurveyOutcomeSendService.already_delivered(session)
