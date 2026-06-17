from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.abuu.agent.agent import AbuuAgentLoop
from app.abuu.agent.pending_action import is_cart_inquiry
from app.abuu.agent.intent_gate import is_menu_browse_request
from app.abuu.agent.session import load_session
from app.abuu.agent.turn_router import classify_turn, resolve_turn, try_turn_router_reply
from app.abuu.agent.intent_gate import freeze_turn_restaurant_snapshot
from app.abuu.models.entities import Restaurant
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService


CHICKEN_ID = "abuu-rest-chicken"
SWEETS_ID = "abuu-rest-sweets"
VEGETARIAN_ID = "abuu-rest-vegetarian"


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
        if db.get(Restaurant, SWEETS_ID) is None:
            pytest.skip("sweets restaurant not seeded")
        yield db


@pytest.fixture
def deepseek_configured():
    with patch(
        "app.abuu.agent.agent.ProviderSettingsService.get_platform_config_decrypted",
        return_value=({"api_key": "test-key"}, True),
    ):
        yield


MATRIX = [
    (
        "menu_not_cart",
        "\u0637\u064a\u0628 \u062d\u0644\u0648\u064a\u0627\u062a \u063a\u0632\u0629 \u0627\u064a\u0634 \u0641\u064a \u0627\u0644\u0645\u0646\u064a\u0648 \u0628\u062a\u0627\u0639 \u062d\u0644\u0648\u064a\u0627\u062a \u063a\u0632\u0629",
        False,
        True,
        "phase1_select_and_menu",
    ),
    (
        "cart_explicit",
        "\u0634\u0648 \u0639\u0646\u062f\u064a \u0641\u064a \u0627\u0644\u0633\u0644\u0629\u061f",
        True,
        False,
        "phase1_cart_summary",
    ),
]


@pytest.mark.parametrize("case,text,is_cart,menu_browse,branch", MATRIX)
def test_slot_classification(case, text, is_cart, menu_browse, branch, abuu_seeded, phase1_env):
    del case, branch
    assert is_cart_inquiry(text, menu_browse=menu_browse) is is_cart
    assert is_menu_browse_request(text) is menu_browse


@patch("app.services.providers.openai_service.OpenAIProviderService.complete_chat_raw")
def test_sweets_menu_switch_from_chicken(mock_complete, abuu_seeded, deepseek_configured, phase1_env):
    mock_complete.side_effect = AssertionError("deterministic router should handle sweets menu")
    db = abuu_seeded
    phone = "+972509993001"
    text = "\u0637\u064a\u0628 \u062d\u0644\u0648\u064a\u0627\u062a \u063a\u0632\u0629 \u0627\u064a\u0634 \u0641\u064a \u0627\u0644\u0645\u0646\u064a\u0648 \u0628\u062a\u0627\u0639 \u062d\u0644\u0648\u064a\u0627\u062a \u063a\u0632\u0629"

    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        AbuuOrderDraftService.upsert_session(
            abuu_db,
            phone=phone,
            step="browsing",
            context={"restaurant_id": CHICKEN_ID, "restaurant_selected": True},
            active_order_id=None,
        )
        abuu_db.commit()
        result = AbuuAgentLoop.run(abuu_db, main_db, phone=phone, text=text, input_source="voice")
        abuu_db.commit()
        session = load_session(abuu_db, phone)

    assert result["restaurant_id"] == SWEETS_ID
    assert "\u0627\u0644\u0633\u0644\u0629 \u0641\u0627\u0636\u064a\u0629" not in result["reply"]
    assert "\u0645\u0646\u064a\u0648" in result["reply"] or "\u062d\u0644\u0648\u064a\u0627\u062a" in result["reply"]
    mock_complete.assert_not_called()


def test_resolve_turn_menu_beats_cart(abuu_seeded, phase1_env):
    db = abuu_seeded
    phone = "+972509993002"
    customer = AbuuOrderDraftService.get_or_create_customer(db, phone, lang="ar")
    session = load_session(db, phone)
    session.restaurant_id = CHICKEN_ID
    session.context["restaurant_selected"] = True
    ranked = freeze_turn_restaurant_snapshot(db, session, customer_id=customer.id)
    text = "\u0637\u064a\u0628 \u062d\u0644\u0648\u064a\u0627\u062a \u063a\u0632\u0629 \u0627\u064a\u0634 \u0641\u064a \u0627\u0644\u0645\u0646\u064a\u0648 \u0628\u062a\u0627\u0639 \u062d\u0644\u0648\u064a\u0627\u062a \u063a\u0632\u0629"
    decision = resolve_turn(db, session, customer=customer, user_text=text, ranked_rows=ranked)
    assert decision.action == "switch_and_menu"
    assert decision.restaurant_id == SWEETS_ID
