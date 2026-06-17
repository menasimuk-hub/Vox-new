"""Tests for pending-state turn resolver (conversation_turn)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.abuu.agent.conversation_turn import (
    classify_turn_intent,
    resolve_and_execute_pending_turn,
    resolve_pending_turn,
)
from app.abuu.agent.gaza_context import refresh_menu_item_index
from app.abuu.agent.pending_action import (
    build_proposal_lines,
    get_pending_action,
    set_pending_add_items,
)
from app.abuu.agent.session import load_session, save_session
from app.abuu.agent.turn_router import try_turn_router_reply
from app.abuu.conversation.orchestrator import AbuuConversationOrchestrator
from app.abuu.models.entities import Restaurant, RestaurantMenuItem
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService


VEGETARIAN_ID = "abuu-rest-vegetarian"
ITEM_VEG_1 = "abuu-item-veg-1"
ITEM_VEG_2 = "abuu-item-veg-2"
ITEM_VEG_3 = "abuu-item-veg-3"


@pytest.fixture
def phase1_env():
    with patch.dict(
        os.environ,
        {
            "ABUU_AGENT_PHASE1_ORCHESTRATION": "true",
            "ABUU_AGENT_WAITER_MODE": "false",
            "ABUU_AGENT_ENABLED": "true",
            "ABUU_CONVERSATION_MODE": "orchestrator",
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


def _setup_single_pending(db, phone: str, *, name_override: str | None = None):
    customer = AbuuOrderDraftService.get_or_create_customer(db, phone, lang="ar")
    session = load_session(db, phone)
    if name_override:
        item = db.get(RestaurantMenuItem, ITEM_VEG_1)
        if item:
            item.name_ar = name_override
            db.add(item)
            db.flush()
    stored, total, delivery = build_proposal_lines(
        db,
        restaurant_id=VEGETARIAN_ID,
        items=[{"menu_item_id": ITEM_VEG_1, "quantity": 1}],
        lang="ar",
    )
    set_pending_add_items(
        session,
        restaurant_id=VEGETARIAN_ID,
        items=stored,
        total_agorot=total,
        delivery_fee_agorot=delivery,
    )
    refresh_menu_item_index(db, session, restaurant_id=VEGETARIAN_ID, lang="ar")
    save_session(db, session)
    db.commit()
    return customer, load_session(db, phone)


def _setup_multi_pending(db, phone: str):
    customer = AbuuOrderDraftService.get_or_create_customer(db, phone, lang="ar")
    session = load_session(db, phone)
    stored, total, delivery = build_proposal_lines(
        db,
        restaurant_id=VEGETARIAN_ID,
        items=[
            {"menu_item_id": ITEM_VEG_1, "quantity": 1},
            {"menu_item_id": ITEM_VEG_2, "quantity": 1},
        ],
        lang="ar",
    )
    set_pending_add_items(
        session,
        restaurant_id=VEGETARIAN_ID,
        items=stored,
        total_agorot=total,
        delivery_fee_agorot=delivery,
    )
    refresh_menu_item_index(db, session, restaurant_id=VEGETARIAN_ID, lang="ar")
    save_session(db, session)
    db.commit()
    return customer, load_session(db, phone)


def test_qty_update_single_pending(abuu_seeded):
    db, _ = abuu_seeded
    phone = "+972509993001"
    customer, session = _setup_single_pending(db, phone, name_override="رز بالدجاج")

    decision = resolve_pending_turn(db, session, customer=customer, user_text="بدي ثلاثة رز بالدجاج")
    assert decision is not None
    assert decision.action == "update_pending_quantity"
    assert decision.branch != "transactional_pending_clarify"

    reply, branch, action = resolve_and_execute_pending_turn(
        db, session, customer=customer, user_text="بدي ثلاثة رز بالدجاج"
    )
    save_session(db, session)
    db.commit()

    pending = get_pending_action(load_session(db, phone))
    assert pending is not None
    assert pending["items"][0]["quantity"] == 3
    assert "pending_clarify" not in branch
    assert action == "update_pending_quantity"
    assert "أضيفهم" in reply or "المجموع" in reply


def test_multi_add_in_pending(abuu_seeded):
    db, _ = abuu_seeded
    phone = "+972509993002"
    customer, session = _setup_single_pending(db, phone)

    reply, branch, action = resolve_and_execute_pending_turn(
        db, session, customer=customer, user_text="1 2 3"
    )
    save_session(db, session)
    db.commit()

    pending = get_pending_action(load_session(db, phone))
    assert pending is not None
    assert action == "add_more_items_to_pending"
    assert len(pending["items"]) >= 2
    assert "pending_clarify" not in branch


def test_qty_token_1x3(abuu_seeded):
    db, _ = abuu_seeded
    phone = "+972509993003"
    customer, session = _setup_single_pending(db, phone)

    resolve_and_execute_pending_turn(db, session, customer=customer, user_text="1*3")
    save_session(db, session)
    db.commit()

    pending = get_pending_action(load_session(db, phone))
    assert pending is not None
    assert pending["items"][0]["quantity"] == 3


def test_natural_multi_pick_bedi_1_wa_3(abuu_seeded, phase1_env):
    db, _ = abuu_seeded
    phone = "+972509993004"
    customer, session = _setup_single_pending(db, phone)

    from app.abuu.agent.menu_pick_parser import parse_menu_pick_tokens

    assert parse_menu_pick_tokens("بدي 1 و 3") == [(1, 1), (3, 1)]


def test_confirm_still_works(abuu_seeded, phase1_env):
    db, _ = abuu_seeded
    phone = "+972509993005"
    customer, session = _setup_multi_pending(db, phone)

    routed = try_turn_router_reply(db, session, customer=customer, user_text="ضيفهم")
    assert routed is not None
    reply, branch, _ = routed
    assert branch == "transactional_pending_confirmed"
    assert "أضفتهم" in reply


def test_cart_during_pending(abuu_seeded, phase1_env):
    db, _ = abuu_seeded
    phone = "+972509993006"
    customer, session = _setup_multi_pending(db, phone)

    decision = resolve_pending_turn(db, session, customer=customer, user_text="show basket")
    assert decision is not None
    assert decision.action == "show_cart"


def test_correction_clears_pending(abuu_seeded, phase1_env):
    db, _ = abuu_seeded
    phone = "+972509993007"
    customer, session = _setup_multi_pending(db, phone)

    reply, branch, action = resolve_and_execute_pending_turn(
        db, session, customer=customer, user_text="لا, بدي سمك"
    )
    save_session(db, session)
    db.commit()

    session = load_session(db, phone)
    assert get_pending_action(session) is None
    assert action == "correction_food_search"


def test_no_false_clarify_on_qty_edit(abuu_seeded, phase1_env):
    db, _ = abuu_seeded
    phone = "+972509993008"
    customer, session = _setup_single_pending(db, phone, name_override="رز بالدجاج")

    intent = classify_turn_intent("بدي ثلاثة رز بالدجاج", session)
    assert intent == "qty_edit"

    routed = try_turn_router_reply(db, session, customer=customer, user_text="بدي ثلاثة رز بالدجاج")
    assert routed is not None
    reply, branch, slots = routed
    assert branch != "transactional_pending_clarify"
    assert "ما فهمت تأكيدك" not in reply


@patch("app.abuu.agent.agent._deepseek_platform_ready", return_value=False)
def test_orchestrator_pending_qty_edit(mock_deepseek, abuu_seeded, phase1_env):
    db, _ = abuu_seeded
    phone = "+972509993009"
    _setup_single_pending(db, phone, name_override="رز بالدجاج")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        result = AbuuConversationOrchestrator.handle(
            abuu_db, main_db, phone=phone, text="بدي ثلاثة رز بالدجاج"
        )
        abuu_db.commit()
        session = load_session(abuu_db, phone)

    assert result["handled"] is True
    assert result["action"] == "update_pending_quantity"
    pending = get_pending_action(session)
    assert pending is not None
    assert pending["items"][0]["quantity"] == 3
    assert "ما فهمت تأكيدك" not in result["reply"]
