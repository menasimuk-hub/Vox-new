"""Tests for the new Smart Waiter Agent (DeepSeek tool-calling pipeline)."""

from __future__ import annotations

import json
import os
import uuid
from unittest.mock import patch

import pytest

from app.abuu.agent.session import load_session, save_session
from app.abuu.menu_intelligence.vocabulary import dump_json_tags
from app.abuu.services.inbound_service import AbuuInboundService
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService
from app.abuu.smart_agent import SmartWaiterAgent
from app.abuu.smart_agent.runner import SmartWaiterAgent as SmartWaiterAgentRunner
from app.abuu.smart_agent.tools import (
    SmartWaiterSkills,
    hydrate_safety_into_session,
    load_customer_safety,
    search_menu_tagged,
)
from app.services.agents.base import AgentToolCall
from app.services.providers.openai_service import OpenAIResponse


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def smart_agent_env():
    env = {
        "ABUU_AGENT_ENABLED": "false",
        "ABUU_CONVERSATION_MODE": "legacy",
        "ABUU_SMART_AGENT_ENABLED": "true",
        "ABUU_SMART_AGENT_ALLOWLIST": "",
        "ABUU_SMART_AGENT_MODEL": "deepseek-chat",
        "ABUU_DEEPSEEK_ENABLED": "true",
        "ABUU_IGNORE_DISTANCE": "true",
        "ABUU_VOICE_INTERPRETATION_ENABLED": "false",
        "ABUU_ALLERGEN_STRICT_MODE": "false",
    }
    with patch.dict(os.environ, env):
        from app.core.config import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()


@pytest.fixture
def abuu_seeded(app_client):
    from sqlalchemy import select

    from app.abuu.models.entities import Restaurant
    from app.abuu.services.agent_settings_seed import seed_agent_settings
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        seed_agent_settings(db)
        db.commit()
        restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
        yield db, restaurant.id, restaurant


@pytest.fixture
def deepseek_configured():
    with patch(
        "app.abuu.agent.agent.ProviderSettingsService.get_platform_config_decrypted",
        return_value=({"api_key": "test-key"}, True),
    ):
        yield


def _text_completion(text: str) -> OpenAIResponse:
    return OpenAIResponse(
        assistant_text=text,
        raw_assistant_message={"role": "assistant", "content": text},
        finish_reason="stop",
    )


def _tool_call(tool_name: str, tool_input: dict) -> OpenAIResponse:
    call_id = f"call_{uuid.uuid4().hex[:6]}"
    raw_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
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
        tool_calls=[AgentToolCall(id=call_id, name=tool_name, arguments=tool_input)],
        raw_assistant_message=raw_msg,
        finish_reason="tool_calls",
    )


# --------------------------------------------------------------------------- #
# Allowlist / routing
# --------------------------------------------------------------------------- #


def test_allowlist_empty_means_all_phones_enabled(smart_agent_env):
    assert SmartWaiterAgent.enabled_for_phone("+972509990001") is True


def test_allowlist_specific_phones(smart_agent_env):
    with patch.dict(os.environ, {"ABUU_SMART_AGENT_ALLOWLIST": "+972509990001,+972509990002"}):
        from app.core.config import get_settings

        get_settings.cache_clear()
        assert SmartWaiterAgent.enabled_for_phone("+972509990001") is True
        assert SmartWaiterAgent.enabled_for_phone("+972509990099") is False


def test_disabled_returns_false_regardless_of_allowlist():
    env = {"ABUU_SMART_AGENT_ENABLED": "false", "ABUU_SMART_AGENT_ALLOWLIST": "+972509990001"}
    with patch.dict(os.environ, env):
        from app.core.config import get_settings

        get_settings.cache_clear()
        assert SmartWaiterAgent.enabled_for_phone("+972509990001") is False


def test_pipeline_name_prefers_smart_agent_over_legacy_agent(smart_agent_env):
    with patch.dict(os.environ, {"ABUU_AGENT_ENABLED": "true", "ABUU_CONVERSATION_MODE": "agent"}):
        from app.core.config import get_settings

        get_settings.cache_clear()
        assert AbuuInboundService._pipeline_name("+972509990001") == "smart_agent"


# --------------------------------------------------------------------------- #
# Tag-enriched search
# --------------------------------------------------------------------------- #


def test_search_menu_tagged_returns_tags_and_ids(abuu_seeded, smart_agent_env):
    _db, restaurant_id, _restaurant = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    phone = "+972509990201"
    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        session.restaurant_id = restaurant_id
        out = search_menu_tagged(
            db,
            restaurant_id=restaurant_id,
            customer=customer,
            session=session,
            query="chicken",
            limit=5,
        )
        assert "id=" in out
        assert "allergens=" in out
        assert "dietary=" in out
        assert "recipe=" in out
        assert "protein=" in out


def test_search_menu_tagged_filters_known_allergy(abuu_seeded, smart_agent_env):
    from sqlalchemy import select

    from app.abuu.models.entities import RestaurantMenuItem
    from app.core.abuu_database import get_abuu_sessionmaker

    _db, restaurant_id, _restaurant = abuu_seeded
    phone = "+972509990202"
    with get_abuu_sessionmaker()() as db:
        items = list(
            db.execute(
                select(RestaurantMenuItem).where(RestaurantMenuItem.is_deleted.is_(False)).limit(2)
            ).scalars().all()
        )
        assert items, "seed should produce menu items"
        target = items[0]
        target.allergen_tags_json = dump_json_tags(["dairy"])
        db.add(target)
        for other in items[1:]:
            other.allergen_tags_json = dump_json_tags([])
            db.add(other)
        db.commit()

        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        session.restaurant_id = restaurant_id
        session.context["allergen_avoid"] = ["dairy"]

        out = search_menu_tagged(
            db,
            restaurant_id=restaurant_id,
            customer=customer,
            session=session,
            query=target.name_en or target.name_ar,
            limit=5,
        )
        assert f"id={target.id}" not in out


# --------------------------------------------------------------------------- #
# set_allergy persistence + hydration
# --------------------------------------------------------------------------- #


def test_set_allergy_persists_to_customer_profile(abuu_seeded, smart_agent_env):
    from app.abuu.models.entities import CustomerProfile
    from app.core.abuu_database import get_abuu_sessionmaker

    _db, restaurant_id, _restaurant = abuu_seeded
    phone = "+972509990203"
    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        session.restaurant_id = restaurant_id

        skills = SmartWaiterSkills(db, session, customer=customer)
        out = skills.execute("set_allergy", {"allergens": ["dairy", "nuts"], "dietary": ["vegan"], "note": "no cheese"})
        assert "dairy" in out or "حساسية" in out
        db.commit()

    with get_abuu_sessionmaker()() as db:
        from sqlalchemy import select

        reloaded = db.execute(select(CustomerProfile).where(CustomerProfile.phone == phone)).scalar_one()
        assert reloaded.allergens_json
        assert "dairy" in reloaded.allergens_json
        assert "nuts" in reloaded.allergens_json
        assert reloaded.dietary_json
        assert "vegan" in reloaded.dietary_json


def test_hydrate_safety_merges_persisted_and_detected(abuu_seeded, smart_agent_env):
    from app.core.abuu_database import get_abuu_sessionmaker

    _db, _restaurant_id, _restaurant = abuu_seeded
    phone = "+972509990204"
    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        customer.allergens_json = json.dumps(["sesame"])
        db.add(customer)
        db.commit()
        persisted_a, persisted_d = load_customer_safety(customer)
        assert "sesame" in persisted_a

        session = load_session(db, phone)
        hydrate_safety_into_session(session, customer, text="بدون حليب لو سمحت")
        merged = session.context.get("allergen_avoid") or []
        assert "sesame" in merged  # persisted
        assert "dairy" in merged  # detected from text


# --------------------------------------------------------------------------- #
# Bulk add_to_cart
# --------------------------------------------------------------------------- #


def test_add_to_cart_bulk_adds_multiple_items(abuu_seeded, smart_agent_env):
    from sqlalchemy import select

    from app.abuu.models.entities import RestaurantMenuItem
    from app.core.abuu_database import get_abuu_sessionmaker

    _db, restaurant_id, _restaurant = abuu_seeded
    phone = "+972509990205"
    with get_abuu_sessionmaker()() as db:
        items = list(
            db.execute(
                select(RestaurantMenuItem)
                .where(
                    RestaurantMenuItem.is_deleted.is_(False),
                    RestaurantMenuItem.is_available.is_(True),
                )
                .limit(2)
            ).scalars().all()
        )
        assert len(items) >= 2

        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        session.restaurant_id = restaurant_id
        session.context["restaurant_id"] = restaurant_id
        session.context["restaurant_selected"] = True

        skills = SmartWaiterSkills(db, session, customer=customer)
        out = skills.execute(
            "add_to_cart",
            {
                "items": [
                    {"item_id": items[0].id, "quantity": 2},
                    {"item_id": items[1].id, "quantity": 1, "notes": "بدون بصل"},
                ]
            },
        )
        assert items[0].name_en in out or items[0].name_ar in out
        assert items[1].name_en in out or items[1].name_ar in out
        # cart should now hold 2 distinct lines
        assert len(session.cart) == 2


# --------------------------------------------------------------------------- #
# Confirm path — single source of truth, no double-send
# --------------------------------------------------------------------------- #


def _seed_default_address(db, customer):
    from app.abuu.services.location_service import save_customer_address

    return save_customer_address(
        db,
        customer_id=customer.id,
        address_text="Test Address, Gaza",
        latitude=31.5,
        longitude=34.45,
        source_message_id=None,
    )


def test_confirm_order_marks_paid_and_notifies_once(abuu_seeded, smart_agent_env):
    from sqlalchemy import select

    from app.abuu.models.entities import AbuuNotification, RestaurantMenuItem
    from app.core.abuu_database import get_abuu_sessionmaker

    _db, restaurant_id, _restaurant = abuu_seeded
    phone = "+972509990206"
    with get_abuu_sessionmaker()() as db:
        item = db.execute(
            select(RestaurantMenuItem)
            .where(
                RestaurantMenuItem.is_deleted.is_(False),
                RestaurantMenuItem.is_available.is_(True),
            )
            .limit(1)
        ).scalar_one()

        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        _seed_default_address(db, customer)
        session = load_session(db, phone)
        session.restaurant_id = restaurant_id
        session.context["restaurant_id"] = restaurant_id
        session.context["restaurant_selected"] = True

        skills = SmartWaiterSkills(db, session, customer=customer)
        skills.execute("add_to_cart", {"items": [{"item_id": item.id, "quantity": 1}]})
        out = skills.execute("confirm_order", {})
        assert "تم تأكيد" in out or "Order confirmed" in out
        db.commit()

        order_id = session.active_order_id
        # Exactly one paid notification per order (UNIQUE constraint + idempotent mark_paid_manual).
        notifications = list(
            db.execute(
                select(AbuuNotification).where(
                    AbuuNotification.order_id == order_id,
                    AbuuNotification.kind == "order_paid",
                    AbuuNotification.target_type == "restaurant",
                )
            ).scalars().all()
        )
        assert len(notifications) == 1


def test_confirm_order_without_address_asks_for_pin(abuu_seeded, smart_agent_env):
    from sqlalchemy import select

    from app.abuu.models.entities import RestaurantMenuItem
    from app.core.abuu_database import get_abuu_sessionmaker

    _db, restaurant_id, _restaurant = abuu_seeded
    phone = "+972509990207"
    with get_abuu_sessionmaker()() as db:
        item = db.execute(
            select(RestaurantMenuItem)
            .where(RestaurantMenuItem.is_available.is_(True))
            .limit(1)
        ).scalar_one()
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        session.restaurant_id = restaurant_id
        session.context["restaurant_id"] = restaurant_id
        session.context["restaurant_selected"] = True

        skills = SmartWaiterSkills(db, session, customer=customer)
        skills.execute("add_to_cart", {"items": [{"item_id": item.id, "quantity": 1}]})
        out = skills.execute("confirm_order", {})
        assert "موقع" in out or "location pin" in out.lower()


# --------------------------------------------------------------------------- #
# End-to-end agent loop with mocked DeepSeek
# --------------------------------------------------------------------------- #


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_smart_agent_arabic_greeting(mock_complete, abuu_seeded, deepseek_configured, smart_agent_env):
    _db, _restaurant_id, _restaurant = abuu_seeded
    mock_complete.return_value = _text_completion("أهلاً! هاي المطاعم المتاحة، شو حابب تأكل؟")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509990208"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        result = SmartWaiterAgentRunner.run(abuu_db, main_db, phone=phone, text="مرحبا")
    assert result["action"] == "smart_agent_reply"
    assert "أهلاً" in result["reply"] or "هاي" in result["reply"]


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_smart_agent_tool_loop_search_then_reply(mock_complete, abuu_seeded, deepseek_configured, smart_agent_env):
    _db, restaurant_id, _restaurant = abuu_seeded
    # Loop: first turn -> search_menu tool call ; second turn -> final text reply.
    mock_complete.side_effect = [
        _tool_call("search_menu", {"query": "chicken"}),
        _text_completion("هاي 2 خيارات لذيذة بدون مكسرات 🍗"),
    ]

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509990209"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        session = load_session(abuu_db, phone)
        session.restaurant_id = restaurant_id
        session.context["restaurant_id"] = restaurant_id
        session.context["restaurant_selected"] = True
        save_session(abuu_db, session)
        abuu_db.commit()
        result = SmartWaiterAgentRunner.run(abuu_db, main_db, phone=phone, text="بدي شاورما")
    assert result["action"] == "smart_agent_reply"
    assert "خيارات" in result["reply"] or "🍗" in result["reply"]


@patch("app.abuu.smart_agent.runner.SmartWaiterAgent.run")
@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_inbound_routes_to_smart_agent_when_allowlisted(mock_send, mock_run, app_client, abuu_seeded, smart_agent_env):
    from app.core.database import get_sessionmaker
    from app.models.organisation import Organisation

    mock_run.return_value = {"handled": True, "action": "smart_agent_reply", "reply": "أهلاً!"}

    with get_sessionmaker()() as db:
        org = Organisation(name="Smart Agent Org")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = f"+97250{uuid.uuid4().int % 10_000_000:07d}"
    with get_sessionmaker()() as db:
        result = AbuuInboundService.try_handle(
            db,
            from_phone=phone,
            body="yallasay",
            message_id=f"smart-{uuid.uuid4().hex[:8]}",
            org_id=org_id,
        )

    assert result.get("handled") is True
    mock_run.assert_called_once()
    mock_send.assert_called()
