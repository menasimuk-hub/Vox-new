"""Inbound integration tests for SmartPipeline-enabled waiter flow."""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest

from app.abuu.agent.session import load_session
from app.abuu.services.inbound_service import AbuuInboundService
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService
from app.abuu.waiter.smart_pipeline import FORBIDDEN_REPLY_FRAGMENTS


@pytest.fixture
def smart_waiter_env():
    env = {
        "ABUU_AGENT_ENABLED": "true",
        "ABUU_CONVERSATION_MODE": "waiter_v2",
        "SMART_PIPELINE_ENABLED": "true",
        "ABUU_DEEPSEEK_ENABLED": "false",
        "ABUU_IGNORE_DISTANCE": "true",
    }
    with patch.dict(os.environ, env):
        from app.core.config import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()


@pytest.fixture
def abuu_seeded(app_client):
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        db.commit()
        yield db


def _assert_no_forbidden(reply: str | None) -> None:
    text = str(reply or "")
    for fragment in FORBIDDEN_REPLY_FRAGMENTS:
        assert fragment not in text, f"forbidden {fragment!r} in {text!r}"


@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_yallasay_then_djaj_inbound(mock_send, mock_llm, app_client, abuu_seeded, smart_waiter_env):
    """E2E-1: Start → category must not hit empty food_search template."""
    from app.abuu.waiter.deepseek_client import DeepSeekResult
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_llm.return_value = DeepSeekResult(text="", fallback_used=True)

    with get_sessionmaker()() as db:
        org = Organisation(name="Smart WA Org")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = f"+97250{uuid.uuid4().int % 10_000_000:07d}"
    msg_id = f"msg-smart-{uuid.uuid4().hex[:10]}"

    with get_abuu_sessionmaker()() as abuu_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        customer.name = "Qusay"
        abuu_db.add(customer)
        abuu_db.commit()

    with get_sessionmaker()() as db:
        start = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="Yallasay",
            message_id=msg_id,
            org_id=org_id,
        )
    assert start.get("handled") is True

    with get_sessionmaker()() as db:
        result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="دجاج",
            message_id=f"{msg_id}-djaj",
            org_id=org_id,
        )

    assert result.get("handled") is True
    assert mock_send.called
    last_body = mock_send.call_args.args[2] if len(mock_send.call_args.args) > 2 else mock_send.call_args.kwargs.get("body", "")
    _assert_no_forbidden(last_body)
    assert "دجاج" in last_body or "شاور" in last_body or "المطاعم" in last_body or "1." in last_body


@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_start_order_binds_restaurant_in_session(mock_send, mock_llm, app_client, abuu_seeded, smart_waiter_env):
    """E2E-2: After Yallasay start, waiter session should retain restaurant."""
    from app.abuu.waiter.deepseek_client import DeepSeekResult
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation
    from app.abuu.services.order_draft_service import AbuuOrderDraftService

    mock_llm.return_value = DeepSeekResult(text="", fallback_used=True)

    with get_sessionmaker()() as db:
        org = Organisation(name="Smart WA Org 2")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = f"+97250{uuid.uuid4().int % 10_000_000:07d}"

    with get_abuu_sessionmaker()() as abuu_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        customer.name = "Qusay"
        abuu_db.add(customer)
        abuu_db.commit()

    with get_sessionmaker()() as db:
        AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="yallasay",
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            org_id=org_id,
        )

    with get_abuu_sessionmaker()() as abuu_db:
        session = load_session(abuu_db, phone)
        ctx = session.context or {}
        assert ctx.get("restaurant_selected") is True
        assert session.restaurant_id is not None
