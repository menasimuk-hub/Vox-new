from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from app.abuu.agent.agent import AbuuAgentLoop
from app.abuu.agent.intent_gate import freeze_turn_restaurant_snapshot, resolve_restaurant_ref
from app.abuu.agent.session import load_session
from app.abuu.agent.tool_guard import execute_tool_guarded, session_state_snapshot
from app.abuu.models.entities import Restaurant
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService
from app.abuu.services.voice_order_debug_service import VoiceOrderDebugService, set_debug_request_id
from app.services.agents.base import AgentToolCall
from app.services.providers.openai_service import OpenAIResponse


FASTFOOD_ID = "abuu-rest-fastfood"
FISH_ID = "abuu-rest-fish"
VEGETARIAN_ID = "abuu-rest-vegetarian"


@pytest.fixture
def phase1_env():
    with patch.dict(
        os.environ,
        {
            "ABUU_AGENT_PHASE1_ORCHESTRATION": "true",
            "ABUU_AGENT_WAITER_MODE": "false",
            "ABUU_AGENT_ENABLED": "true",
            "ABUU_VOICE_ORDER_DEBUG": "true",
        },
    ):
        from app.core.config import get_settings

        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


@pytest.fixture
def abuu_seeded(app_client):
    from sqlalchemy import select

    from app.abuu.services.agent_settings_seed import seed_agent_settings
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        seed_agent_settings(db)
        db.commit()
        fastfood = db.get(Restaurant, FASTFOOD_ID)
        fish = db.get(Restaurant, FISH_ID)
        if fastfood is None or fish is None:
            pytest.skip("Pilot restaurants not seeded")
        yield db, fastfood, fish


@pytest.fixture
def deepseek_configured():
    with patch(
        "app.abuu.agent.agent.ProviderSettingsService.get_platform_config_decrypted",
        return_value=({"api_key": "test-key"}, True),
    ):
        yield


def _tool_response(tool_name: str, tool_input: dict) -> OpenAIResponse:
    tool_id = "call_phase1"
    raw_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tool_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(tool_input),
                },
            }
        ],
    }
    return OpenAIResponse(
        assistant_text="",
        tool_calls=[AgentToolCall(id=tool_id, name=tool_name, arguments=tool_input)],
        raw_assistant_message=raw_msg,
        finish_reason="tool_calls",
    )


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_phase1_fastfood_menu_request_ar(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    _db, fastfood, _fish = abuu_seeded
    mock_complete.side_effect = AssertionError("LLM should not be called for deterministic fast-food menu")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509991001"
    text = "وجبات سريعة، ايش المنيو تاع الوجبات السريعة؟"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        result = AbuuAgentLoop.run(
            abuu_db,
            main_db,
            phone=phone,
            text=text,
            input_source="voice",
            message_id="phase1-ar-1",
        )
        abuu_db.commit()
        session = load_session(abuu_db, phone)

    assert result["restaurant_id"] == FASTFOOD_ID
    assert "برجر" in result["reply"] or "وجبة" in result["reply"]
    assert session.restaurant_id == FASTFOOD_ID
    mock_complete.assert_not_called()


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_phase1_fastfood_menu_request_en(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    _db, fastfood, _fish = abuu_seeded
    mock_complete.side_effect = AssertionError("LLM should not be called")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509991002"
    text = "Wajabat Sari'a Fast Food, show me the menu please"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="en")
        customer.preferred_language = "en"
        abuu_db.add(customer)
        abuu_db.commit()
        result = AbuuAgentLoop.run(
            abuu_db,
            main_db,
            phone=phone,
            text=text,
            input_source="text",
        )
        session = load_session(abuu_db, phone)

    assert result["restaurant_id"] == FASTFOOD_ID
    assert "burger" in result["reply"].lower() or "menu" in result["reply"].lower()
    assert session.restaurant_id == FASTFOOD_ID
    mock_complete.assert_not_called()


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_phase1_category_without_restaurant(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    _db, _fastfood, _fish = abuu_seeded
    mock_complete.side_effect = AssertionError("LLM should not be called for category-only clarify")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509991003"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text="بدي برجر")
        session = load_session(abuu_db, phone)

    assert session.restaurant_id is None
    assert "مطعم" in result["reply"] or "restaurant" in result["reply"].lower()
    mock_complete.assert_not_called()


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_phase1_blocks_empty_change_restaurant(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    _db, _fastfood, fish = abuu_seeded
    mock_complete.return_value = _tool_response("change_restaurant", {})

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509991004"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        order = AbuuOrderDraftService.start_draft(abuu_db, customer=customer, restaurant=fish)
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="browsing",
            context={"restaurant_id": fish.id, "restaurant_selected": True},
            active_order_id=order.id,
        )
        abuu_db.commit()
        before = load_session(abuu_db, phone)
        result = AbuuAgentLoop.run(
            abuu_db,
            main_db,
            phone=phone,
            text="مرحبا",
        )
        after = load_session(abuu_db, phone)

    assert after.restaurant_id == before.restaurant_id == FISH_ID
    assert "change_restaurant blocked" in result["reply"] or "ما قدرت" in result["reply"]


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_phase1_fish_to_fastfood_switch(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    _db, _fastfood, fish = abuu_seeded
    mock_complete.side_effect = AssertionError("deterministic path should handle switch")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker
    from app.abuu.models.entities import RestaurantMenuItem

    phone = "+972509991005"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        order = AbuuOrderDraftService.start_draft(abuu_db, customer=customer, restaurant=fish)
        item = abuu_db.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(RestaurantMenuItem).limit(1)
        ).scalar_one()
        AbuuOrderDraftService.add_item(abuu_db, order, item, quantity=1)
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="browsing",
            context={"restaurant_id": fish.id, "restaurant_selected": True},
            active_order_id=order.id,
        )
        abuu_db.commit()
        result = AbuuAgentLoop.run(
            abuu_db,
            main_db,
            phone=phone,
            text="وجبات سريعة، ايش المنيو تاع الوجبات السريعة؟",
            input_source="voice",
            message_id="phase1-switch-1",
        )
        session = load_session(abuu_db, phone)

    assert session.restaurant_id == FASTFOOD_ID
    assert session.restaurant_id != FISH_ID
    assert "تفريغ" in result["reply"] or "منيو" in result["reply"]


def test_phase1_numeric_pick_uses_frozen_snapshot(abuu_seeded, phase1_env):
    _db, fastfood, _fish = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    phone = "+972509991006"
    with get_abuu_sessionmaker()() as abuu_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        session = load_session(abuu_db, phone)
        rows = freeze_turn_restaurant_snapshot(abuu_db, session, customer_id=customer.id)
        assert len(rows) >= 1
        target_index = None
        for idx, row in enumerate(rows, start=1):
            if row.get("id") == fastfood.id:
                target_index = str(idx)
                break
        assert target_index is not None
        picked = resolve_restaurant_ref(abuu_db, session, target_index)
        assert picked is not None
        assert picked.id == FASTFOOD_ID


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_phase1_stage6_dual_restaurant_fields(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    _db, _fastfood, _fish = abuu_seeded
    mock_complete.side_effect = AssertionError("deterministic")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509991007"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        request_id = VoiceOrderDebugService.begin(
            abuu_db,
            customer_phone=phone,
            message_id="phase1-stage6",
            pipeline="agent",
        )
        set_debug_request_id(request_id)
        AbuuAgentLoop.run(
            abuu_db,
            main_db,
            phone=phone,
            text="وجبات سريعة، ايش المنيو تاع الوجبات السريعة؟",
            input_source="voice",
            message_id="phase1-stage6",
        )
        abuu_db.commit()
        bundle = VoiceOrderDebugService.get_bundle(abuu_db, request_id)

    stage6 = bundle["stages"]["6_final_order"]
    assert stage6["requested_restaurant_id"] == FASTFOOD_ID
    assert stage6["active_order_restaurant_id"] == FASTFOOD_ID
    assert stage6["restaurant_match"] is True
    stage5 = bundle["stages"]["5_parsed"]
    assert stage5["parse_status"] == "ok"
    assert stage5["action"]["branch"] == "phase1_select_and_menu"


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_phase1_vps_stt_fastfood_menu(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    _db, _fastfood, _fish = abuu_seeded
    mock_complete.side_effect = AssertionError("LLM should not be called for VPS STT fast-food menu")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509991009"
    text = "الوجبات السريعة أنت كاتب فوق الوجبات السريعة مدلي أشوف المنيو تبعها"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        request_id = VoiceOrderDebugService.begin(
            abuu_db,
            customer_phone=phone,
            message_id="phase1-vps-stt",
            pipeline="agent",
        )
        set_debug_request_id(request_id)
        result = AbuuAgentLoop.run(
            abuu_db,
            main_db,
            phone=phone,
            text=text,
            input_source="voice",
            message_id="phase1-vps-stt",
        )
        abuu_db.commit()
        session = load_session(abuu_db, phone)
        bundle = VoiceOrderDebugService.get_bundle(abuu_db, request_id)

    assert result["restaurant_id"] == FASTFOOD_ID
    assert session.restaurant_id == FASTFOOD_ID
    assert "منيو" in result["reply"] or "برجر" in result["reply"] or "وجبة" in result["reply"]
    assert "[id=" not in result["reply"]
    stage5 = bundle["stages"]["5_parsed"]
    assert stage5["parse_status"] == "ok"
    assert stage5["action"]["branch"] == "phase1_select_and_menu"
    mock_complete.assert_not_called()


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_phase1_stage6_skips_stale_cancelled_on_clarify(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    _db, _fastfood, fish = abuu_seeded
    mock_complete.side_effect = AssertionError("clarify path should not call LLM")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509991010"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        order = AbuuOrderDraftService.start_draft(abuu_db, customer=customer, restaurant=fish)
        order.status = "cancelled"
        abuu_db.add(order)
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="browsing",
            context={"restaurant_id": None, "restaurant_selected": False},
            active_order_id=order.id,
        )
        abuu_db.commit()
        request_id = VoiceOrderDebugService.begin(
            abuu_db,
            customer_phone=phone,
            message_id="phase1-clarify-stale",
            pipeline="agent",
        )
        set_debug_request_id(request_id)
        result = AbuuAgentLoop.run(
            abuu_db,
            main_db,
            phone=phone,
            text="بدي اشوف المنيو",
            input_source="voice",
            message_id="phase1-clarify-stale",
        )
        abuu_db.commit()
        session = load_session(abuu_db, phone)
        bundle = VoiceOrderDebugService.get_bundle(abuu_db, request_id)

    assert session.restaurant_id is None
    assert "مطعم" in result["reply"]
    stage5 = bundle["stages"]["5_parsed"]
    assert stage5["action"]["branch"] == "phase1_menu_clarify"
    stage6 = bundle["stages"]["6_final_order"]
    assert stage6["order_id"] is None
    assert stage6["requested_restaurant_id"] is None
    assert stage6["active_order_restaurant_id"] is None
    mock_complete.assert_not_called()


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_phase1_load_session_clears_stale_cancelled_order(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    _db, fastfood, fish = abuu_seeded
    mock_complete.side_effect = AssertionError("deterministic path should handle VPS STT")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509991011"
    stt = "الوجبات السريعة أنت كاتب فوق الوجبات السريعة مدلي أشوف المنيو تبعها"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        stale = AbuuOrderDraftService.start_draft(abuu_db, customer=customer, restaurant=fish)
        stale.status = "cancelled"
        abuu_db.add(stale)
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="browsing",
            context={"restaurant_id": None, "restaurant_selected": False},
            active_order_id=stale.id,
        )
        abuu_db.commit()
        request_id = VoiceOrderDebugService.begin(
            abuu_db,
            customer_phone=phone,
            message_id="phase1-stale-load",
            pipeline="agent",
        )
        set_debug_request_id(request_id)
        result = AbuuAgentLoop.run(
            abuu_db,
            main_db,
            phone=phone,
            text=stt,
            input_source="voice",
            message_id="phase1-stale-load",
        )
        abuu_db.commit()
        session = load_session(abuu_db, phone)
        bundle = VoiceOrderDebugService.get_bundle(abuu_db, request_id)

    assert result["restaurant_id"] == FASTFOOD_ID
    assert session.active_order_id != stale.id
    assert session.restaurant_id == FASTFOOD_ID
    stage6 = bundle["stages"]["6_final_order"]
    assert stage6["requested_restaurant_id"] == FASTFOOD_ID
    assert stage6["active_order_restaurant_id"] == FASTFOOD_ID
    assert stage6["restaurant_match"] is True
    assert stage6["active_order"]["status"] == "draft"
    mock_complete.assert_not_called()


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_phase1_bound_vegetarian_cart_switches_to_fastfood(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    _db, _fastfood, _fish = abuu_seeded
    mock_complete.side_effect = AssertionError("deterministic switch should not call LLM")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker
    from app.abuu.models.entities import RestaurantMenuItem

    phone = "+972509991012"
    text = "وجبات سريعة، إيش المنيو تبع الوجبات السريعة؟"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        vegetarian = abuu_db.get(Restaurant, VEGETARIAN_ID)
        assert vegetarian is not None
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        order = AbuuOrderDraftService.start_draft(abuu_db, customer=customer, restaurant=vegetarian)
        item = abuu_db.get(RestaurantMenuItem, "abuu-item-veg-s1")
        if item is None:
            item = abuu_db.execute(
                __import__("sqlalchemy", fromlist=["select"]).select(RestaurantMenuItem).limit(1)
            ).scalar_one()
        AbuuOrderDraftService.add_item(abuu_db, order, item, quantity=1)
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="browsing",
            context={"restaurant_id": vegetarian.id, "restaurant_selected": True},
            active_order_id=order.id,
        )
        abuu_db.commit()
        request_id = VoiceOrderDebugService.begin(
            abuu_db,
            customer_phone=phone,
            message_id="phase1-veg-switch",
            pipeline="agent",
        )
        set_debug_request_id(request_id)
        result = AbuuAgentLoop.run(
            abuu_db,
            main_db,
            phone=phone,
            text=text,
            input_source="voice",
            message_id="phase1-veg-switch",
        )
        abuu_db.commit()
        session = load_session(abuu_db, phone)
        bundle = VoiceOrderDebugService.get_bundle(abuu_db, request_id)

    assert result["restaurant_id"] == FASTFOOD_ID
    assert session.restaurant_id == FASTFOOD_ID
    assert session.cart == []
    assert "منيو" in result["reply"] or "برجر" in result["reply"]
    assert "[id=" not in result["reply"]
    assert "تفريغ" in result["reply"] or "منيو" in result["reply"]
    stage5 = bundle["stages"]["5_parsed"]
    assert stage5["action"]["branch"] == "phase1_select_and_menu"
    stage6 = bundle["stages"]["6_final_order"]
    assert stage6["requested_restaurant_id"] == FASTFOOD_ID
    assert stage6["restaurant_match"] is True
    mock_complete.assert_not_called()


def test_phase1_guard_blocks_change_restaurant_no_mutation(abuu_seeded, phase1_env):
    _db, _fastfood, fish = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    phone = "+972509991008"
    with get_abuu_sessionmaker()() as abuu_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        session = load_session(abuu_db, phone)
        session.restaurant_id = fish.id
        session.context["restaurant_id"] = fish.id
        session.context["restaurant_selected"] = True
        freeze_turn_restaurant_snapshot(abuu_db, session, customer_id=customer.id)
        before = session_state_snapshot(session)
        result = execute_tool_guarded(
            abuu_db,
            session,
            customer=customer,
            tool_name="change_restaurant",
            tool_input={},
            user_text="وجبات سريعة، ايش المنيو؟",
        )
        after = session_state_snapshot(session)

    assert "change_restaurant blocked" in result
    assert after["restaurant_id"] == before["restaurant_id"] == FISH_ID
