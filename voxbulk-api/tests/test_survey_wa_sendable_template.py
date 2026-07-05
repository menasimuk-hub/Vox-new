"""Tests for Meta sendable template resolution (welcome clone name mismatch)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models.organisation import Organisation
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_system_template_service import (
    WELCOME_TEMPLATE_NAMED_NAME,
    SurveySystemTemplateService,
)
from app.services.survey_whatsapp_conversation_service import _send_message
from app.services.survey_whatsapp_template_service import (
    resolve_sendable_template_row,
    template_row_is_sendable_on_meta,
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


def _welcome_row(
    db,
    *,
    name: str,
    status: str = "APPROVED",
    telnyx_record_id: str | None = None,
    parent_template_id: int | None = None,
    active: bool = True,
) -> TelnyxWhatsappTemplate:
    record_id = telnyx_record_id or str(uuid.uuid4())
    components = [
        {"type": "BODY", "text": "Hi {{1}}! Tap Start."},
        {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Start"}]},
    ]
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=record_id,
        template_id=record_id if not str(record_id).startswith("local_") else str(uuid.uuid4()),
        name=name,
        display_name=name,
        language="en_US",
        category="UTILITY",
        body_preview="Hi {{1}}! Tap Start.",
        step_role="start",
        status=status,
        active_for_survey=active,
        variant_type="standard",
        privacy_mode="off",
        components_json=json.dumps(components),
        parent_template_id=parent_template_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_template_row_is_sendable_on_meta():
    approved = MagicMock(status="APPROVED", telnyx_record_id=str(uuid.uuid4()))
    assert template_row_is_sendable_on_meta(approved) is True

    local = MagicMock(status="LOCAL_DRAFT", telnyx_record_id="local_abc")
    assert template_row_is_sendable_on_meta(local) is False

    pending = MagicMock(status="PENDING", telnyx_record_id=str(uuid.uuid4()))
    assert template_row_is_sendable_on_meta(pending) is False


def test_resolve_sendable_prefers_active_successor_over_inactive_approved_parent(db):
    parent = _welcome_row(
        db,
        name="welcome_parent",
        status="APPROVED",
        telnyx_record_id=str(uuid.uuid4()),
        active=False,
    )
    clone = _welcome_row(
        db,
        name="welcome_parent_utu_2",
        status="APPROVED",
        parent_template_id=int(parent.id),
        active=True,
    )

    sendable = resolve_sendable_template_row(db, parent)
    assert sendable is not None
    assert sendable.id == clone.id


def test_resolve_order_welcome_uses_wizard_selection_first(db):
    from app.services.survey_system_template_service import SurveySystemTemplateService

    named = _welcome_row(
        db,
        name="wizard_named_welcome",
        status="APPROVED",
        telnyx_record_id=str(uuid.uuid4()),
        active=True,
    )
    named.privacy_mode = "off"
    db.add(named)
    anon = _welcome_row(
        db,
        name="system_anonymous_welcome",
        status="APPROVED",
        telnyx_record_id=str(uuid.uuid4()),
        active=True,
    )
    anon.privacy_mode = "on"
    anon.body_preview = "Hi there! Anonymous system copy"
    db.add(anon)
    db.commit()

    config = {
        "anonymous_responses": False,
        "welcome_template_id": int(named.id),
        "wa_template_id": int(named.id),
    }
    resolved = SurveySystemTemplateService.resolve_order_welcome_template_row(db, config)
    assert resolved is not None
    assert resolved.id == named.id

    parent = _welcome_row(
        db,
        name=WELCOME_TEMPLATE_NAMED_NAME,
        status="LOCAL_DRAFT",
        telnyx_record_id="local_parent",
        active=True,
    )
    clone = _welcome_row(
        db,
        name=f"{WELCOME_TEMPLATE_NAMED_NAME}_utu_2",
        status="APPROVED",
        parent_template_id=int(parent.id),
        active=True,
    )

    sendable = resolve_sendable_template_row(db, parent)
    assert sendable is not None
    assert sendable.id == clone.id
    assert sendable.name.endswith("_utu_2")


def test_resolve_welcome_returns_sendable_clone_not_stale_parent(db):
    parent = _welcome_row(
        db,
        name=WELCOME_TEMPLATE_NAMED_NAME,
        status="LOCAL_DRAFT",
        telnyx_record_id="local_parent",
        active=True,
    )
    clone = _welcome_row(
        db,
        name=f"{WELCOME_TEMPLATE_NAMED_NAME}_utu_2",
        status="APPROVED",
        parent_template_id=int(parent.id),
        active=True,
    )

    resolved = SurveySystemTemplateService.resolve_welcome_template_for_survey(
        db,
        {"anonymous_responses": False},
    )
    assert resolved is not None
    assert resolved.id == clone.id
    assert resolved.name.endswith("_utu_2")


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_send_message_uses_clone_template_name_for_stale_config_id(mock_send, db):
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.survey_whatsapp_conversation_service import _send_message

    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")

    org = Organisation(name="Sendable Org")
    db.add(org)
    db.commit()

    stale = _welcome_row(
        db,
        name="welcome_start",
        status="LOCAL_DRAFT",
        telnyx_record_id="local_stale",
    )
    clone = _welcome_row(
        db,
        name="welcome_start_utu_2",
        status="APPROVED",
        parent_template_id=int(stale.id),
    )

    order = ServiceOrder(
        id="ord-1",
        org_id=org.id,
        user_id="user-1",
        service_code="survey",
        title="Test",
        status="running",
        payment_status="approved",
        config_json="{}",
    )
    recipient = ServiceOrderRecipient(
        id="rec-1",
        order_id=order.id,
        row_number=1,
        name="Alex",
        phone="+447700900123",
        status="pending",
        result_json="{}",
    )
    db.add(order)
    db.add(recipient)
    db.commit()

    assert _send_message(
        db,
        order=order,
        recipient=recipient,
        body="Hi Alex! Tap Start.",
        config={"wa_builder_test": True},
        template_row=stale,
    )

    assert mock_send.called
    kwargs = mock_send.call_args.kwargs
    assert kwargs.get("template_name") == clone.name


def test_assert_runtime_template_send_follows_approved_clone(db):
    from app.services.survey_builder_runtime_service import (
        assert_runtime_template_send,
        attach_builder_runtime_to_config,
        build_builder_runtime,
    )

    stale = _welcome_row(
        db,
        name="middle_rating_q",
        status="LOCAL_DRAFT",
        telnyx_record_id="local_stale",
    )
    clone = _welcome_row(
        db,
        name="middle_rating_q_utu_2",
        status="APPROVED",
        parent_template_id=int(stale.id),
    )

    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="svc-quality",
        survey_type_name="Service quality",
        privacy_mode="off",
        welcome_template_id=stale.id,
        middle_template_ids=[stale.id],
    )
    config = attach_builder_runtime_to_config({"wa_builder_test": True}, runtime)

    row = assert_runtime_template_send(db, config, stale.id, context="test_middle_step")
    assert row.id == clone.id
    assert row.name.endswith("_utu_2")
