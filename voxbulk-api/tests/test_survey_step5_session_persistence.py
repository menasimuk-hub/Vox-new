"""Step 5 must persist awaiting-start session before welcome send succeeds."""

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
from app.services.survey_builder_runtime_service import attach_builder_runtime_to_config, build_builder_runtime
from app.services.survey_builder_test_service import SurveyBuilderTestService
from app.services.survey_session_service import SurveySessionService


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


@patch("app.services.survey_whatsapp_conversation_service.TelnyxMessagingService.send_whatsapp")
def test_step5_persists_session_before_welcome(mock_send, db):
    mock_send.return_value = MagicMock(ok=True, status="sent", channel="whatsapp", detail="ok")
    org = Organisation(name="Session First Org")
    db.add(org)
    db.commit()

    welcome = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="welcome",
        display_name="welcome",
        language="en_US",
        category="MARKETING",
        body_preview="Hi",
        step_role="start",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Hi"}]),
    )
    q1 = TelnyxWhatsappTemplate(
        telnyx_record_id=str(uuid.uuid4()),
        template_id=str(uuid.uuid4()),
        name="q1",
        display_name="q1",
        language="en_US",
        category="MARKETING",
        body_preview="Rate",
        step_role="rating",
        status="APPROVED",
        active_for_survey=True,
        variant_type="standard",
        components_json=json.dumps([{"type": "BODY", "text": "Rate"}]),
    )
    db.add_all([welcome, q1])
    db.commit()

    runtime = build_builder_runtime(
        db,
        industry_id=None,
        survey_type_id="svc-quality",
        survey_type_name="Service quality",
        privacy_mode="off",
        welcome_template_id=welcome.id,
        middle_template_ids=[q1.id],
    )
    config = attach_builder_runtime_to_config(
        {
            "delivery": "whatsapp",
            "survey_channel": "whatsapp",
            "channels": ["whatsapp"],
            "wa_template_id": welcome.id,
        },
        runtime,
    )
    order = ServiceOrder(
        id=str(uuid.uuid4()),
        org_id=org.id,
        user_id="user-1",
        service_code="survey",
        title="Session first",
        status="draft",
        payment_status="approved",
        recipient_count=1,
        config_json=json.dumps(config),
        run_mode="scheduled",
        scheduled_start_at=datetime.utcnow() - timedelta(hours=1),
        scheduled_end_at=datetime.utcnow() + timedelta(hours=2),
    )
    db.add(order)
    db.commit()

    with patch(
        "app.services.survey_whatsapp_conversation_service._send_message",
        return_value=True,
    ) as mock_opening_send:
        result = SurveyBuilderTestService.start_wa_test_session(
            db,
            org_id=org.id,
            user_id="user-1",
            order_id=order.id,
            test_phone="+447954823445",
        )

    assert result["session_id"] is not None
    assert result["trace_id"]
    assert result["status"] == "active"
    mock_opening_send.assert_called_once()

    session = SurveySessionService.verify_active_awaiting_start(
        db,
        result["recipient_id"],
        order_id=order.id,
        trace_id=result["trace_id"],
    )
    assert session.id == result["session_id"]
    assert int(session.current_step or 0) == 0
