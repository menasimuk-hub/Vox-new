"""Tests for propose_add_to_cart same-turn reply and semantic pending confirms."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from app.abuu.agent.agent import AbuuAgentLoop
from app.abuu.agent.pending_action import (
    get_pending_action,
    is_affirmative_reply,
    score_pending_intent,
)
from app.abuu.agent.session import load_session
from app.abuu.models.entities import Restaurant
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService
from app.services.agents.base import AgentToolCall
from app.services.providers.openai_service import OpenAIResponse


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


def _tool_response(tool_name: str, tool_input: dict) -> OpenAIResponse:
    tool_id = "call_propose"
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
def test_propose_add_to_cart_returns_same_turn_reply(
    mock_complete,
    abuu_seeded,
    deepseek_configured,
    phase1_env,
):
    _db, veg = abuu_seeded
    mock_complete.side_effect = [
        _tool_response(
            "propose_add_to_cart",
            {
                "restaurant_id": veg.id,
                "items": [
                    {"menu_item_id": ITEM_VEG_1, "quantity": 2},
                    {"menu_item_id": ITEM_VEG_2, "quantity": 1},
                ],
            },
        ),
        AssertionError("Second LLM turn must not run after successful propose_add_to_cart"),
    ]

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509994001"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="browsing",
            context={"restaurant_id": veg.id, "restaurant_selected": True},
            active_order_id=None,
        )
        abuu_db.commit()
        result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text="بدي طبقين خضار وساندwich")
        abuu_db.commit()
        session = load_session(abuu_db, phone)

    assert get_pending_action(session) is not None
    assert "كيف أقدر أساعدك" not in result["reply"]
    assert "أضيفهم" in result["reply"] or "المجموع" in result["reply"]
    assert mock_complete.call_count == 1


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_voice_confirm_composite_phrase(
    mock_complete,
    abuu_seeded,
    deepseek_configured,
    phase1_env,
):
    from app.abuu.agent.pending_action import (
        build_proposal_lines,
        set_pending_add_items,
    )
    from app.abuu.agent.gaza_context import refresh_menu_item_index
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    mock_complete.side_effect = AssertionError("confirm should be deterministic")

    phone = "+972509994002"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        session = load_session(abuu_db, phone)
        stored, total, delivery = build_proposal_lines(
            abuu_db,
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
        refresh_menu_item_index(abuu_db, session, restaurant_id=VEGETARIAN_ID, lang="ar")
        from app.abuu.agent.session import save_session

        save_session(abuu_db, session)
        abuu_db.commit()

        result = AbuuAgentLoop.run(
            abuu_db,
            main_db,
            phone=phone,
            text="تمام تمام ضيفوا مع السلة",
            input_source="voice",
        )
        abuu_db.commit()
        session = load_session(abuu_db, phone)

    assert get_pending_action(session) is None
    assert len(session.cart) >= 1
    assert "كيف أقدر أساعدك" not in result["reply"]
    mock_complete.assert_not_called()


@pytest.mark.parametrize(
    "text,expected_intent",
    [
        ("تمام تمام ضيفوا مع السلة", "confirm"),
        ("أيوة حطه بالسلة", "confirm"),
        ("3 رز بالدجاج", "qty_edit"),
        ("زيدها 3", "qty_edit"),
    ],
)
def test_score_pending_intent_semantic(text, expected_intent):
    intent, confidence = score_pending_intent(text)
    assert intent == expected_intent
    assert confidence >= 0.45


def test_is_affirmative_composite():
    assert is_affirmative_reply("تمام تمام ضيفوا مع السلة")
    assert is_affirmative_reply("أيوة حطه بالسلة")
