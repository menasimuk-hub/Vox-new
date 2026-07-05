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


def test_build_preview_uses_live_names_not_meta_examples(db):
    from app.services.survey_whatsapp_template_service import (
        SurveyWhatsappTemplateService,
        template_row_has_buttons,
    )

    components = [
        {
            "type": "BODY",
            "text": "Hi {{1}}! Thanks for visiting {{2}}.",
            "example": {"body_text": [["jack", "Toyota service center"]]},
        },
        {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Start survey"}]},
    ]
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="welcome_named",
        language="en_US",
        category="UTILITY",
        body_preview="Hi {{1}}! Thanks for visiting {{2}}.",
        step_role="start",
        status="APPROVED",
        components_json=json.dumps(components),
        example_values_json=json.dumps(["jack", "Toyota service center"]),
    )
    db.add(row)
    db.commit()

    preview = SurveyWhatsappTemplateService.build_preview(
        db,
        row,
        business_name="Demo Dental",
        first_name="demo",
    )
    body = str(preview.get("rendered_body") or "")
    assert "demo" in body
    assert "Demo Dental" in body
    assert "jack" not in body.lower()
    assert "toyota" not in body.lower()
    assert template_row_has_buttons(row) is True


def test_effective_components_merges_remote_buttons_when_draft_body_only(db):
    from app.services.survey_whatsapp_template_service import (
        _effective_components,
        template_row_has_buttons,
        template_row_needs_meta_approval,
    )

    remote = [
        {"type": "BODY", "text": "Hi {{1}}, welcome."},
        {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Start survey"}]},
    ]
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="voxbulk_survey_welcome_templates_standard_utu_2",
        language="en_US",
        category="UTILITY",
        body_preview="Hi {{1}}, welcome.",
        step_role="start",
        status="APPROVED",
        components_json=json.dumps(remote),
        draft_components_json=json.dumps([{"type": "BODY", "text": "Hi {{1}}, welcome."}]),
    )
    db.add(row)
    db.commit()

    merged = _effective_components(row)
    assert template_row_has_buttons(row) is True
    assert template_row_needs_meta_approval(row) is True
    assert any(str(c.get("type") or "").upper() == "BUTTONS" for c in merged if isinstance(c, dict))


@patch("app.services.survey_whatsapp_conversation_service._send_whatsapp_template")
def test_welcome_without_local_buttons_still_uses_hsm_send(mock_hsm, db):
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.services.survey_whatsapp_conversation_service import _send_message

    mock_hsm.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")

    org = Organisation(name="Demo Org")
    db.add(org)
    db.commit()

    row = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="voxbulk_survey_welcome_templates_standard_utu_2",
        language="en_US",
        category="UTILITY",
        body_preview="Hi {{1}}, tap to start.",
        step_role="start",
        status="APPROVED",
        components_json=json.dumps([{"type": "BODY", "text": "Hi {{1}}, tap to start."}]),
        draft_components_json=json.dumps([{"type": "BODY", "text": "Hi {{1}}, tap to start."}]),
    )
    db.add(row)
    db.commit()

    order = ServiceOrder(
        id="ord-welcome-hsm",
        org_id=org.id,
        user_id="user-1",
        service_code="survey",
        title="Test",
        status="running",
        payment_status="approved",
        config_json="{}",
    )
    recipient = ServiceOrderRecipient(
        id="rec-welcome-hsm",
        order_id=order.id,
        row_number=1,
        name="demo",
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
        body="Hi demo, tap to start.",
        config={"wa_builder_test": True},
        template_row=row,
    )

    assert mock_hsm.called


def _order_recipient(db, org):
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient

    order = ServiceOrder(
        id=f"ord-{uuid.uuid4().hex[:8]}",
        org_id=org.id,
        user_id="user-1",
        service_code="survey",
        title="Test",
        status="running",
        payment_status="approved",
        config_json="{}",
    )
    recipient = ServiceOrderRecipient(
        id=f"rec-{uuid.uuid4().hex[:8]}",
        order_id=order.id,
        row_number=1,
        name="demo",
        phone="+447700900123",
        status="pending",
        result_json="{}",
    )
    db.add(order)
    db.add(recipient)
    db.commit()
    return order, recipient


def _session_text_row(
    db,
    *,
    name: str,
    step_role: str,
    body: str,
    components: list[dict] | None = None,
) -> TelnyxWhatsappTemplate:
    comps = components or [{"type": "BODY", "text": body}]
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name=name,
        display_name=name,
        language="en_US",
        category="UTILITY",
        body_preview=body,
        step_role=step_role,
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        privacy_mode="off",
        components_json=json.dumps(comps),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_whatsapp_conversation_service._send_whatsapp_template")
def test_tell_us_more_approved_uses_session_not_hsm(mock_hsm, mock_session, db):
    org = Organisation(name="Demo Org")
    db.add(org)
    db.commit()

    row = _session_text_row(
        db,
        name="voxbulk_survey_tell_us_more_global_tell_us_more",
        step_role="reason",
        body="Sorry to hear that. What went wrong?",
    )
    order, recipient = _order_recipient(db, org)
    mock_session.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")

    assert _send_message(
        db,
        order=order,
        recipient=recipient,
        body=row.body_preview,
        config={"wa_builder_test": True},
        template_row=row,
    )

    assert mock_session.called
    assert not mock_hsm.called


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_whatsapp_conversation_service._send_whatsapp_template")
def test_final_feedback_approved_uses_session_not_hsm(mock_hsm, mock_session, db):
    org = Organisation(name="Demo Org")
    db.add(org)
    db.commit()

    row = _session_text_row(
        db,
        name="voxbulk_survey_final_feedback_global_final_feedback",
        step_role="final_feedback_text",
        body="Is there anything else you would like to share?",
    )
    order, recipient = _order_recipient(db, org)
    mock_session.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")

    assert _send_message(
        db,
        order=order,
        recipient=recipient,
        body=row.body_preview,
        config={"wa_builder_test": True},
        template_row=row,
    )

    assert mock_session.called
    assert not mock_hsm.called


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
@patch("app.services.survey_whatsapp_conversation_service._send_whatsapp_template")
def test_tell_us_more_with_legacy_buttons_still_uses_session(mock_hsm, mock_session, db):
    org = Organisation(name="Demo Org")
    db.add(org)
    db.commit()

    row = _session_text_row(
        db,
        name="tell_us_more_variant_1",
        step_role="reason",
        body="Would you like to tell us more?",
        components=[
            {"type": "BODY", "text": "Would you like to tell us more?"},
            {
                "type": "BUTTONS",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Yes"},
                    {"type": "QUICK_REPLY", "text": "No"},
                ],
            },
        ],
    )
    order, recipient = _order_recipient(db, org)
    mock_session.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")

    assert _send_message(
        db,
        order=order,
        recipient=recipient,
        body=row.body_preview,
        config={"wa_builder_test": True},
        template_row=row,
    )

    assert mock_session.called
    assert not mock_hsm.called


def test_template_row_must_send_as_session_text_for_no_button_kinds(db):
    from app.services.survey_whatsapp_template_service import (
        template_row_must_send_as_session_text,
        template_row_needs_meta_approval,
    )

    thank = _session_text_row(
        db,
        name="thank_you_variant_1",
        step_role="completion",
        body="Thank you for your feedback.",
    )
    assert template_row_must_send_as_session_text(thank) is True
    assert template_row_needs_meta_approval(thank) is False

    rating = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="service_quality_rating_q1",
        display_name="service_quality_rating_q1",
        language="en_US",
        category="UTILITY",
        body_preview="How was your visit?",
        step_role="rating",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        privacy_mode="off",
        components_json=json.dumps(
            [
                {"type": "BODY", "text": "How was your visit?"},
                {
                    "type": "BUTTONS",
                    "buttons": [
                        {"type": "QUICK_REPLY", "text": "Excellent"},
                        {"type": "QUICK_REPLY", "text": "Good"},
                        {"type": "QUICK_REPLY", "text": "Poor"},
                    ],
                },
            ]
        ),
    )
    db.add(rating)
    db.commit()
    assert template_row_must_send_as_session_text(rating) is False
    assert template_row_needs_meta_approval(rating) is True


def test_survey_template_to_dict_strips_legacy_done_for_thank_you(db):
    from app.services.survey_whatsapp_template_service import survey_template_to_dict

    row = _session_text_row(
        db,
        name="voxbulk_survey_thank_you_standard",
        step_role="completion",
        body="Thank you {{1}} for your feedback.",
        components=[
            {"type": "BODY", "text": "Thank you {{1}} for your feedback."},
            {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Done"}]},
        ],
    )
    row.draft_components_json = json.dumps([{"type": "BODY", "text": "Thank you {{1}} for your feedback."}])
    db.add(row)
    db.commit()
    db.refresh(row)

    payload = survey_template_to_dict(row)
    assert payload["send_mode"] == "session_text"
    assert payload["buttons"] == []
