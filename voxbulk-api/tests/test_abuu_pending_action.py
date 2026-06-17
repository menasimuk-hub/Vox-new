"""Regression tests for Abuu transactional pending cart confirmation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.abuu.agent.agent import AbuuAgentLoop
from app.abuu.agent.pending_action import (
    apply_pending_add_items,
    build_proposal_lines,
    get_pending_action,
    is_affirmative_reply,
    is_cart_inquiry,
    set_pending_add_items,
)
from app.abuu.agent.session import load_session, save_session
from app.abuu.agent.turn_router import try_turn_router_reply
from app.abuu.agent.intent_gate import try_deterministic_reply
from app.abuu.models.entities import Restaurant
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService


VEGETARIAN_ID = "abuu-rest-vegetarian"
ITEM_VEG_1 = "abuu-item-veg-1"
ITEM_VEG_2 = "abuu-item-veg-2"


@pytest.fixture
def phase1_env():
    with patch.dict(
        os.environ,
        {
            "ABUU_AGENT_PHASE1_ORCHESTRATION": "true",
            "ABUU_AGENT_WAITER_MODE": "false",
            "ABUU_AGENT_ENABLED": "true",
        },
    ):
        from app.core.config import get_settings

        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


@pytest.fixture
def abuu_seeded(app_client):
    from app.abuu.services.agent_settings_seed import seed_agent_settings
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        seed_agent_settings(db)
        db.commit()
        veg = db.get(Restaurant, VEGETARIAN_ID)
        if veg is None:
            pytest.skip("Vegetarian restaurant not seeded")
        yield db, veg


@pytest.fixture
def deepseek_configured():
    with patch(
        "app.abuu.agent.agent.ProviderSettingsService.get_platform_config_decrypted",
        return_value=({"api_key": "test-key"}, True),
    ):
        yield


def _setup_pending_session(db, phone: str, *, restaurant_id: str = VEGETARIAN_ID):
    customer = AbuuOrderDraftService.get_or_create_customer(db, phone, lang="ar")
    session = load_session(db, phone)
    stored, total, delivery = build_proposal_lines(
        db,
        restaurant_id=restaurant_id,
        items=[
            {"menu_item_id": ITEM_VEG_1, "quantity": 1},
            {"menu_item_id": ITEM_VEG_2, "quantity": 1},
        ],
        lang="ar",
    )
    set_pending_add_items(
        session,
        restaurant_id=restaurant_id,
        items=stored,
        total_agorot=total,
        delivery_fee_agorot=delivery,
    )
    session.restaurant_id = None
    session.context.pop("restaurant_selected", None)
    save_session(db, session)
    db.commit()
    return customer, session


@pytest.mark.parametrize(
    "reply",
    ["ضيفهم", "ضيفهم على السلة", "تمام", "نعم", "ok"],
)
def test_affirmative_replies_match(reply):
    assert is_affirmative_reply(reply)


def test_apply_pending_adds_items(abuu_seeded):
    db, _veg = abuu_seeded
    phone = "+972509992001"
    customer, session = _setup_pending_session(db, phone)
    session = load_session(db, phone)
    assert session.restaurant_id == VEGETARIAN_ID

    reply = apply_pending_add_items(db, session, customer=customer)
    save_session(db, session)
    db.commit()

    session = load_session(db, phone)
    assert get_pending_action(session) is None
    assert len(session.cart) == 2
    assert session.restaurant_id == VEGETARIAN_ID
    assert "أضفتهم" in reply or "تمام" in reply


@pytest.mark.parametrize("confirm_text", ["ضيفهم", "ضيفهم على السلة", "تمام"])
@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_agent_pending_confirm(mock_complete, abuu_seeded, deepseek_configured, phase1_env, confirm_text):
    db, _veg = abuu_seeded
    mock_complete.side_effect = AssertionError("LLM should not run for pending confirmation")
    phone = "+972509992002"
    _setup_pending_session(db, phone)

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text=confirm_text)
        abuu_db.commit()
        session = load_session(abuu_db, phone)

    assert len(session.cart) >= 2
    assert session.restaurant_id == VEGETARIAN_ID
    assert get_pending_action(session) is None
    mock_complete.assert_not_called()
    assert "أضفتهم" in result["reply"] or "السلة" in result["reply"]


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_cart_inquiry_after_add_not_menu_clarify(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    db, _veg = abuu_seeded
    mock_complete.side_effect = AssertionError("cart inquiry should be deterministic")
    phone = "+972509992003"
    customer, _session = _setup_pending_session(db, phone)
    apply_pending_add_items(db, _session, customer=customer)
    save_session(db, _session)
    db.commit()

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text="شو عندي في السلة؟")
        abuu_db.commit()

    assert is_cart_inquiry("شو عندي في السلة؟")
    assert "من أي مطعم" not in result["reply"]
    assert "السلة" in result["reply"] or "المجموع" in result["reply"]
    mock_complete.assert_not_called()


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_pending_blocks_numeric_restaurant_pick(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    db, _veg = abuu_seeded
    mock_complete.side_effect = AssertionError("numeric pick during pending should not list restaurants")
    phone = "+972509992004"
    _setup_pending_session(db, phone)

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text="5")
        abuu_db.commit()

    assert "اعرض المطاعم" not in result["reply"] or "نعم" in result["reply"]
    assert "من أي مطعm" not in result["reply"]
    assert "من أي مطعم" not in result["reply"]
    mock_complete.assert_not_called()


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_explicit_restaurant_list_clears_pending(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    db, _veg = abuu_seeded
    mock_complete.side_effect = AssertionError("restaurant list should be deterministic")
    phone = "+972509992005"
    _setup_pending_session(db, phone)

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text="اعرض المطاعم")
        abuu_db.commit()
        session = load_session(abuu_db, phone)

    assert get_pending_action(session) is None
    assert "مطعm" in result["reply"] or "مطعم" in result["reply"] or "Restaurant" in result["reply"]
    mock_complete.assert_not_called()


def test_expired_pending_not_applied(abuu_seeded):
    db, _veg = abuu_seeded
    phone = "+972509992006"
    customer, session = _setup_pending_session(db, phone)
    pending = session.context["pending_action"]
    pending["expires_at"] = (datetime.utcnow() - timedelta(minutes=1)).isoformat(timespec="seconds")
    session.context["pending_action"] = pending
    save_session(db, session)
    db.commit()

    session = load_session(db, phone)
    assert get_pending_action(session) is None

    assert try_turn_router_reply(db, session, customer=customer, user_text="نعم") is None


def test_binding_restored_from_pending_on_load(abuu_seeded, phase1_env):
    db, _veg = abuu_seeded
    phone = "+972509992007"
    customer = AbuuOrderDraftService.get_or_create_customer(db, phone, lang="ar")
    AbuuOrderDraftService.upsert_session(
        db,
        phone=phone,
        step="browsing",
        context={
            "pending_action": {
                "type": "add_items_to_cart",
                "restaurant_id": VEGETARIAN_ID,
                "items": [{"menu_item_id": ITEM_VEG_1, "quantity": 1, "price_agorot": 4500}],
                "total_agorot": 4500,
                "delivery_fee_agorot": 0,
                "expires_at": (datetime.utcnow() + timedelta(minutes=10)).isoformat(timespec="seconds"),
            },
            "active_flow": "cart_confirmation",
            "bound_restaurant_id": VEGETARIAN_ID,
        },
        active_order_id=None,
    )
    db.commit()

    session = load_session(db, phone)
    assert session.restaurant_id == VEGETARIAN_ID
    assert session.context.get("restaurant_selected") is True

    routed = try_turn_router_reply(db, session, customer=customer, user_text="تمام")
    assert routed is not None
    text, branch, _slots = routed
    assert branch == "transactional_pending_confirmed"
    assert "أضفتهم" in text


def test_intent_gate_cart_summary_not_menu_clarify(abuu_seeded, phase1_env):
    db, _veg = abuu_seeded
    phone = "+972509992008"
    customer = AbuuOrderDraftService.get_or_create_customer(db, phone, lang="ar")
    session = load_session(db, phone)
    session.restaurant_id = VEGETARIAN_ID
    session.context["restaurant_selected"] = True
    session.context["active_flow"] = "ordering"

    result = try_deterministic_reply(
        db,
        session,
        customer=customer,
        user_text="شو عندي في السلة حاليا؟",
    )
    assert result is not None
    reply, branch = result
    assert branch in {"phase1_cart_summary", "transactional_cart_summary"}
    assert "من أي مطعm" not in reply
    assert "من أي مطعم" not in reply
