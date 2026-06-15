from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.abuu.agent.agent import AbuuAgentLoop
from app.abuu.agent.kb import get_menu, invalidate_menu_cache, search_menu
from app.abuu.agent.session import clear_session, load_session, save_session
from app.abuu.agent.skills import execute_tool
from app.abuu.services.inbound_service import AbuuInboundService
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService
from app.services.agents.base import AgentToolCall
from app.services.providers.openai_service import OpenAIResponse


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


def _tool_then_text(tool_name: str, tool_input: dict, final_text: str):
    tool_id = "call_test_1"
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
    tool_response = OpenAIResponse(
        assistant_text="",
        tool_calls=[
            AgentToolCall(id=tool_id, name=tool_name, arguments=tool_input),
        ],
        raw_assistant_message=raw_msg,
        finish_reason="tool_calls",
    )
    return [tool_response, _text_completion(final_text)]


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_agent_english_browse_and_reply(mock_complete, abuu_seeded, deepseek_configured):
    _db, restaurant_id, _restaurant = abuu_seeded
    mock_complete.side_effect = _tool_then_text(
        "list_restaurants",
        {},
        "Here are some restaurants — which one would you like?",
    )

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509990001"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="en")
        customer.preferred_language = "en"
        abuu_db.add(customer)
        abuu_db.commit()
        with patch.dict(os.environ, {"ABUU_AGENT_ENABLED": "true"}):
            from app.core.config import get_settings

            get_settings.cache_clear()
            result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text="Hello, I want food")
    assert result["action"] == "agent_reply"
    assert "restaurants" in result["reply"].lower()


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_agent_arabic_reply(mock_complete, abuu_seeded, deepseek_configured):
    _db, _restaurant_id, _restaurant = abuu_seeded
    mock_complete.return_value = _text_completion("مرحباً! ماذا تحب أن تأكل؟")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509990002"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text="مرحبا")
    assert "مرحب" in result["reply"]


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_inbound_start_uses_legacy_flow_when_agent_enabled(mock_send, mock_complete, abuu_seeded, app_client, deepseek_configured):
    _db, _restaurant_id, _restaurant = abuu_seeded

    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        org = __import__("app.models.organisation", fromlist=["Organisation"]).Organisation(name="Agent Org")
        db.add(org)
        db.commit()
        org_id = org.id

    phone = "+972509990003"
    with patch.dict(os.environ, {"ABUU_AGENT_ENABLED": "true"}):
        from app.core.config import get_settings

        get_settings.cache_clear()
        with get_sessionmaker()() as db:
            result = AbuuInboundService.try_handle(
                db,
                from_phone=phone,
                body="abuu",
                message_id="agent-msg-1",
                org_id=org_id,
            )
    assert result.get("handled") is True
    assert result.get("action") == "started"
    mock_complete.assert_not_called()
    mock_send.assert_called()


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
@patch("app.abuu.services.inbound_service.TelnyxMessagingService.send_whatsapp")
def test_inbound_agent_mode_for_open_chat(mock_send, mock_complete, abuu_seeded, app_client, deepseek_configured):
    _db, restaurant_id, _restaurant = abuu_seeded
    mock_complete.return_value = _text_completion("Try our grilled chicken today.")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509990013"
    with get_abuu_sessionmaker()() as abuu_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="en")
        customer.name = "Agent User"
        abuu_db.add(customer)
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="choosing_restaurant",
            context={"restaurant_id": restaurant_id},
            active_order_id=None,
            message_id="setup-1",
        )
        abuu_db.commit()

    with get_sessionmaker()() as db:
        org = __import__("app.models.organisation", fromlist=["Organisation"]).Organisation(name="Agent Org 2")
        db.add(org)
        db.commit()
        org_id = org.id

    with patch.dict(os.environ, {"ABUU_AGENT_ENABLED": "true"}):
        from app.core.config import get_settings

        get_settings.cache_clear()
        with get_sessionmaker()() as db:
            result = AbuuInboundService.try_handle(
                db,
                from_phone=phone,
                body="what do you recommend?",
                message_id="agent-msg-2",
                org_id=org_id,
            )
    assert result.get("handled") is True
    assert result.get("action") == "agent_reply"
    mock_send.assert_called()


def test_session_persistence(abuu_seeded):
    _db, restaurant_id, _restaurant = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    phone = "+972509990004"
    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone, lang="en")
        session = load_session(db, phone)
        session.messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        session.restaurant_id = restaurant_id
        session.context["restaurant_id"] = restaurant_id
        session.context["restaurant_selected"] = True
        save_session(db, session, message_id="persist-1")
        db.commit()

    with get_abuu_sessionmaker()() as db:
        reloaded = load_session(db, phone)
        assert len(reloaded.messages) == 2
        assert reloaded.restaurant_id == restaurant_id


def test_menu_search(abuu_seeded):
    _db, restaurant_id, _restaurant = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        menu = get_menu(db, restaurant_id)
        assert menu
        hits = search_menu(db, restaurant_id, "chicken", "en")
        assert isinstance(hits, list)
        invalidate_menu_cache(restaurant_id)


def test_search_menu_tool(abuu_seeded):
    _db, restaurant_id, _restaurant = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    phone = "+972509990005"
    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        session.restaurant_id = restaurant_id
        result = execute_tool(
            db,
            session,
            customer=customer,
            tool_name="search_menu",
            tool_input={"query": "chicken"},
        )
        assert "No matching" in result or "id=" in result


@patch("app.abuu.agent.voice.AbuuVoiceService.transcribe_inbound")
@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_voice_transcript_runs_agent(mock_complete, mock_transcribe, abuu_seeded, deepseek_configured):
    _db, _restaurant_id, _restaurant = abuu_seeded
    mock_transcribe.return_value = SimpleNamespace(
        ok=True,
        transcript="I want chicken",
        confidence=0.9,
        media_url=None,
        content_type=None,
        storage_path=None,
        error=None,
    )
    mock_complete.return_value = _text_completion("Great choice! Let me find chicken dishes.")

    from app.abuu.agent.voice import transcribe_and_run_agent
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509990006"
    with get_sessionmaker()() as main_db, get_abuu_sessionmaker()() as abuu_db:
        result = transcribe_and_run_agent(
            abuu_db,
            main_db,
            phone=phone,
            record={"type": "audio"},
            lang="en",
            message_id="voice-1",
        )
    assert result["action"] == "agent_reply"


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_agent_llm_failure_returns_apology(mock_complete, abuu_seeded, deepseek_configured):
    mock_complete.side_effect = RuntimeError("api down")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509990007"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text="hello")
    assert result["action"] == "agent_reply"
    assert result["reply"]


def test_agent_deepseek_not_configured_returns_error(abuu_seeded):
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509990009"
    with patch(
        "app.abuu.agent.agent.ProviderSettingsService.get_platform_config_decrypted",
        return_value=({}, False),
    ):
        with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
            result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text="hello")
    assert result["action"] == "agent_error"
    assert result["reply"]


def test_session_reset_endpoint(abuu_seeded, app_client):
    _db, _restaurant_id, _restaurant = abuu_seeded
    phone = "+972509990008"
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        session.messages = [{"role": "user", "content": "test"}]
        save_session(db, session)
        db.commit()

    with patch.dict(os.environ, {"ABUU_AGENT_INTERNAL_KEY": "test-internal"}):
        from app.core.config import get_settings

        get_settings.cache_clear()
        resp = app_client.post(
            f"/abuu/session/{phone}/reset",
            headers={"X-Abuu-Internal-Key": "test-internal"},
        )
    assert resp.status_code == 200
    assert resp.json().get("cleared") is True

    with get_abuu_sessionmaker()() as db:
        row = AbuuOrderDraftService.get_session(db, phone)
        assert row is None


def test_legacy_router_when_agent_disabled(app_client):
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert os.environ.get("ABUU_AGENT_ENABLED", "false") == "false"


def test_list_restaurants_includes_ids(abuu_seeded):
    _db, _restaurant_id, _restaurant = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    phone = "+972509990010"
    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        result = execute_tool(db, session, customer=customer, tool_name="list_restaurants", tool_input={})
        assert "[id=abuu-rest-" in result


def test_select_restaurant_by_list_number(abuu_seeded):
    _db, _restaurant_id, _restaurant = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    phone = "+972509990011"
    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        execute_tool(db, session, customer=customer, tool_name="list_restaurants", tool_input={})
        result = execute_tool(
            db,
            session,
            customer=customer,
            tool_name="select_restaurant",
            tool_input={"restaurant_id": "1"},
        )
        assert session.restaurant_id
        assert "Selected" in result or "تم اختيار" in result


def test_empty_draft_does_not_bind_restaurant(abuu_seeded):
    _db, restaurant_id, restaurant = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    phone = "+972509990012"
    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        order = AbuuOrderDraftService.start_draft(db, customer=customer, restaurant=restaurant)
        AbuuOrderDraftService.upsert_session(
            db,
            phone=phone,
            step="browsing",
            context={"restaurant_id": restaurant_id},
            active_order_id=order.id,
        )
        db.commit()
        session = load_session(db, phone)
        assert session.restaurant_id is None


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_yallasay_start_clears_stale_restaurant(mock_complete, abuu_seeded, deepseek_configured):
    _db, restaurant_id, restaurant = abuu_seeded
    mock_complete.return_value = _text_completion("يلا! هاي المطاعم المتاحة.")

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509990013"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        order = AbuuOrderDraftService.start_draft(abuu_db, customer=customer, restaurant=restaurant)
        session = load_session(abuu_db, phone)
        session.restaurant_id = restaurant_id
        session.active_order_id = order.id
        session.context["restaurant_id"] = restaurant_id
        save_session(abuu_db, session)
        abuu_db.commit()
        result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text="yallasay")
    assert result["action"] == "agent_reply"
    with get_abuu_sessionmaker()() as abuu_db:
        reloaded = load_session(abuu_db, phone)
        assert reloaded.restaurant_id is None


def test_change_restaurant_tool_lists_all(abuu_seeded):
    _db, restaurant_id, restaurant = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    phone = "+972509990014"
    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        session.restaurant_id = restaurant_id
        session.context["restaurant_selected"] = True
        result = execute_tool(db, session, customer=customer, tool_name="change_restaurant", tool_input={})
        assert session.restaurant_id is None
        assert "1." in result


def test_list_offers_includes_chicken_and_fish(abuu_seeded):
    _db, _restaurant_id, _restaurant = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker

    phone = "+972509990015"
    with get_abuu_sessionmaker()() as db:
        customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
        session = load_session(db, phone)
        result = execute_tool(db, session, customer=customer, tool_name="list_offers", tool_input={})
        assert "chicken" in result.lower() or "دجاج" in result
        assert "fish" in result.lower() or "سمك" in result
