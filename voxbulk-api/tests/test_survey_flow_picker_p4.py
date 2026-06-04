"""P4: constrained AI picker for graph survey branching."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.wa_survey_platform_settings import WaSurveyPlatformSettings
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_flow_compiler_service import compile_linear_graph
from app.services.survey_flow_config_service import attach_flow_to_config
from app.services.survey_flow_constants import NEXT_RESOLUTION_AI_ASSISTED
from app.services.survey_flow_engine_service import SurveyFlowEngineService
from app.services.survey_flow_picker_service import SurveyFlowPickerService
from app.services.survey_picker_settings_service import SurveyPickerSettingsService
from app.services.survey_session_service import SurveySessionService
from app.services.survey_wa_test_pack_seed_service import SurveyWaTestPackSeedService
from app.services.survey_whatsapp_conversation_service import handle_inbound_reply, send_first_question


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
        SurveyPickerSettingsService.ensure_row(session)
        yield session
    finally:
        session.close()


def _ai_graph_config() -> dict:
    page_roles = ["start", "rating", "yes_no", "reason", "completion"]
    questions = [
        {"step_role": "rating", "text": "Rate", "reply_type": "rating", "options": ["1", "2", "3", "4", "5"]},
        {"step_role": "yes_no", "text": "OK?", "reply_type": "true_false", "options": ["Yes", "No"]},
        {"step_role": "reason", "text": "Why?", "reply_type": "long_text", "options": []},
    ]
    snap = compile_linear_graph(
        page_roles=page_roles,
        questions=questions,
        max_question_visits=6,
        closing_body="Thanks",
        branches=[
            {
                "from_step_role": "rating",
                "to_step_role": "unhappy",
                "priority": 5,
                "rule_key": "branch.low",
                "condition": {"op": "lte", "source": "last_answer.normalized_value", "value": "2", "cast": "int"},
            },
            {
                "from_step_role": "rating",
                "to_step_role": "reason",
                "priority": 12,
                "rule_key": "branch.to_reason",
                "condition": {"op": "lte", "source": "last_answer.normalized_value", "value": "10", "cast": "int"},
            },
        ],
    )
    snap = SurveyFlowPickerService.patch_snapshot_for_ai_test(snap)
    base = {
        "survey_channel": "whatsapp",
        "channels": ["whatsapp"],
        "survey_type_id": str(uuid.uuid4()),
        "page_roles": page_roles,
        "whatsapp_flow": {"questions": questions, "page_roles": page_roles, "closing": "Thanks"},
        "ai_picker_enabled": True,
        "simulator_mock_picker": True,
    }
    return attach_flow_to_config(base, snapshot=snap, flow_definition_id=None)


def _order(config: dict) -> ServiceOrder:
    return ServiceOrder(
        id=str(uuid.uuid4()),
        org_id="org-1",
        user_id="user-1",
        service_code="survey",
        title="Picker test",
        status="running",
        payment_status="approved",
        recipient_count=1,
        quote_total_pence=0,
        config_json=json.dumps(config),
    )


def test_build_candidates_outgoing_edges_only(db):
    pack = SurveyWaTestPackSeedService.ensure_test_pack(db)
    config = _ai_graph_config()
    config["survey_type_id"] = pack["survey_type"]["id"]
    order = _order(config)
    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        row_number=1,
        name="T",
        phone="+447700900999",
        status="sent",
    )
    db.add(order)
    db.add(recipient)
    db.commit()

    with patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp") as mock_send:
        mock_send.return_value = type("R", (), {"ok": True, "detail": "ok", "channel": "whatsapp"})()
        send_first_question(db, order=order, recipient=recipient, config=config)

    session = SurveySessionService.get_by_recipient(db, recipient.id)
    snap, idx = SurveyFlowEngineService.load_indexed(config)
    node = idx["nodes"]["rating"]
    assert node.get("next_resolution") == NEXT_RESOLUTION_AI_ASSISTED
    candidates = SurveyFlowPickerService.build_candidates(
        db,
        session=session,
        config=config,
        snap=snap,
        idx=idx,
        current_node_key="rating",
        visit_num=1,
    )
    keys = {c["node_key"] for c in candidates}
    assert "yes_no" in keys
    assert "reason" in keys or "outcome_unhappy" in keys


@patch("app.services.survey_outcome_send_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_mock_picker_on_rating_node(mock_send, mock_wa, db):
    mock_send.return_value = type("R", (), {"ok": True, "detail": "ok", "channel": "whatsapp"})()
    mock_wa.return_value = type("R", (), {"ok": True, "detail": "ok", "channel": "whatsapp", "external_id": "x"})()

    pack = SurveyWaTestPackSeedService.ensure_test_pack(db)
    config = _ai_graph_config()
    config["survey_type_id"] = pack["survey_type"]["id"]
    order = _order(config)
    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        row_number=1,
        name="T",
        phone="+447700900111",
        status="sent",
    )
    db.add(order)
    db.add(recipient)
    db.commit()

    send_first_question(db, order=order, recipient=recipient, config=config)
    handle_inbound_reply(db, from_phone=recipient.phone, body="4", org_id=order.org_id)

    session = SurveySessionService.get_by_recipient(db, recipient.id)
    dbg = SurveyFlowPickerService.latest_picker_debug(db, session.id)
    assert dbg is not None
    assert dbg.get("picker_called") is True
    assert dbg.get("chosen_node_key")
    assert int(session.picker_invocation_count or 0) == 1


def test_platform_kill_switch_skips_ai(db):
    row = db.get(WaSurveyPlatformSettings, "default")
    row.ai_picker_enabled = False
    db.add(row)
    db.commit()
    assert SurveyPickerSettingsService.is_platform_picker_enabled(db) is False
