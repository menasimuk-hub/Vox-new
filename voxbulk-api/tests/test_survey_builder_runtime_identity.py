"""Preview/runtime identity — builder_runtime is the single source of truth."""

from __future__ import annotations

import uuid

import pytest

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_flow_service import resolve_conversation_step
from app.services.survey_builder_runtime_service import (
    SurveyBuilderFlowError,
    attach_builder_runtime_to_config,
    build_builder_runtime,
    compute_runtime_hash,
    load_builder_runtime,
    runtime_step_sequence,
)
from app.services.survey_flow_config_service import is_graph_flow
from app.services.survey_whatsapp_conversation_service import survey_questions_from_config


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


def test_preview_runtime_same_template_ids_and_hash(db):
    q1 = _tpl(db, name="hospitality_q1", body="How was the food?", step_role="rating")
    q2 = _tpl(db, name="hospitality_q2", body="Would you return?", step_role="yes_no")
    welcome = _tpl(db, name="welcome_tpl", body="Hi {{1}}", step_role="start")
    thank = _tpl(db, name="thank_tpl", body="Thanks {{1}}", step_role="completion")

    runtime = build_builder_runtime(
        db,
        industry_id="ind-hospitality",
        survey_type_id="svc-quality",
        survey_type_name="Service quality",
        privacy_mode="off",
        welcome_template_id=welcome.id,
        middle_template_ids=[q1.id, q2.id],
        thank_you_template_id=thank.id,
    )
    preview_ids = [q1.id, q2.id]
    runtime_ids = [int(x) for x in runtime["middle_template_ids"]]
    assert preview_ids == runtime_ids
    assert runtime["hash"] == compute_runtime_hash(runtime)

    order_config = attach_builder_runtime_to_config({"survey_type_id": "svc-quality"}, runtime)
    assert is_graph_flow(order_config) is False
    assert runtime_step_sequence(order_config) == runtime["step_sequence"]
    assert survey_questions_from_config(order_config) == runtime["step_sequence"]

    step1 = resolve_conversation_step(order_config, 1)
    step2 = resolve_conversation_step(order_config, 2)
    assert step1["template_id"] == q1.id
    assert step2["template_id"] == q2.id
    assert step1["source"] == "order.config_json.builder_runtime"


def test_non_selected_template_hard_fails(db):
    allowed = _tpl(db, name="allowed", body="Allowed?", step_role="yes_no")
    rogue = _tpl(db, name="rogue_service_quality", body="Thank you, Live", step_role="abc_choice")
    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="svc-quality",
        survey_type_name="Service quality",
        privacy_mode="off",
        welcome_template_id=allowed.id,
        middle_template_ids=[allowed.id],
    )
    config = attach_builder_runtime_to_config({}, runtime)
    from app.services.survey_builder_runtime_service import assert_runtime_template_send

    with pytest.raises(SurveyBuilderFlowError, match="builder flow violation"):
        assert_runtime_template_send(db, config, rogue.id, context="test")
