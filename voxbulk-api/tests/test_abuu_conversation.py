"""Tests for Abuu conversational orchestrator (Gaza waiter)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.abuu.agent.session import Session as AgentSession
from app.abuu.agent.session_persist import fit_context_json_size, prepare_context_for_storage
from app.abuu.conversation.fact_bundle import FactBundleLoader
from app.abuu.conversation.intent_router import IntentRouter
from app.abuu.conversation.orchestrator import AbuuConversationOrchestrator
from app.abuu.conversation.restaurant_guard import RestaurantGuard, RestaurantMismatchError
from app.abuu.conversation.wa_sanitize import wa_customer_sanitize
from app.abuu.services.agent_settings_seed import seed_agent_settings
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService


@pytest.fixture
def abuu_seeded(app_client):
    from sqlalchemy import select

    from app.abuu.models.entities import Restaurant
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        seed_agent_settings(db)
        db.commit()
        restaurants = list(db.execute(select(Restaurant).limit(5)).scalars().all())
        yield db, restaurants


def test_wa_sanitize_strips_internal_ids():
    raw = "مطعم (مفتوح) [id=abuu-rest-chicken]\n• دجاج — 45 ₪"
    cleaned = wa_customer_sanitize(raw)
    assert "[id=" not in cleaned
    assert "abuu-rest-" not in cleaned
    assert "دجاج" in cleaned


def test_fish_intent_returns_items_not_restaurants(abuu_seeded):
    db, _restaurants = abuu_seeded
    session = AgentSession(customer_wa_number="+972509991001", language="ar")
    intent = IntentRouter.classify(None, "بدي سمك", session)  # type: ignore[arg-type]
    assert intent.name == "food_search"

    bundle = FactBundleLoader.load(db, intent, session, customer=None)
    assert bundle.customer_lines
    joined = "\n".join(bundle.customer_lines)
    assert "[id=" not in joined
    assert "abuu-rest-" not in joined


def test_cross_restaurant_guard_blocks_mix(abuu_seeded):
    db, restaurants = abuu_seeded
    if len(restaurants) < 2:
        pytest.skip("need at least 2 restaurants")

    phone = "+972509991002"
    customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
    rest_a = restaurants[0]
    rest_b = restaurants[1]

    order = AbuuOrderDraftService.start_draft(db, customer=customer, restaurant=rest_a)
    items_a = AbuuOrderDraftService.list_menu_items(db, rest_a.id, limit=1)
    assert items_a
    order = AbuuOrderDraftService.add_item(db, order, items_a[0])

    items_b = AbuuOrderDraftService.list_menu_items(db, rest_b.id, limit=1)
    assert items_b
    rest_b_row = db.get(type(rest_a), rest_b.id)

    guard = RestaurantGuard.try_add_item(
        db,
        customer=customer,
        order=order,
        context={"restaurant_id": rest_a.id, "restaurant_selected": True},
        item=items_b[0],
        restaurant=rest_b_row,
        lang="ar",
    )
    assert not guard.ok
    assert guard.action == "cross_restaurant_blocked"


def test_ensure_order_raises_on_cross_restaurant_cart(abuu_seeded):
    db, restaurants = abuu_seeded
    if len(restaurants) < 2:
        pytest.skip("need at least 2 restaurants")

    customer = AbuuOrderDraftService.get_or_create_customer(db, "+972509991003")
    rest_a = restaurants[0]
    rest_b = restaurants[1]
    order = AbuuOrderDraftService.start_draft(db, customer=customer, restaurant=rest_a)
    items = AbuuOrderDraftService.list_menu_items(db, rest_a.id, limit=1)
    order = AbuuOrderDraftService.add_item(db, order, items[0])

    with pytest.raises(RestaurantMismatchError):
        AbuuOrderDraftService.ensure_order(
            db,
            customer=customer,
            restaurant=rest_b,
            existing_order=order,
        )


def test_orchestrator_greet_no_internal_ids(abuu_seeded):
    _db, _restaurants = abuu_seeded
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509991004"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        abuu_db.commit()
        with patch.dict(
            os.environ,
            {
                "ABUU_AGENT_ENABLED": "true",
                "ABUU_CONVERSATION_MODE": "orchestrator",
                "ABUU_DEEPSEEK_ENABLED": "false",
            },
        ):
            from app.core.config import get_settings

            get_settings.cache_clear()
            result = AbuuConversationOrchestrator.handle(
                abuu_db,
                main_db,
                phone=phone,
                text="yallasay",
            )
            abuu_db.commit()
    assert result.get("handled")
    reply = result.get("reply", "")
    assert "[id=" not in reply
    assert "abuu-rest-" not in reply


def test_conversation_mode_enabled():
    with patch.dict(
        os.environ,
        {"ABUU_AGENT_ENABLED": "true", "ABUU_CONVERSATION_MODE": "orchestrator"},
    ):
        from app.core.config import get_settings

        get_settings.cache_clear()
        assert AbuuConversationOrchestrator.conversation_enabled()


def test_session_context_compaction_strips_prefetch_and_caps_messages():
    huge_messages = [
        {"role": "user", "content": f"turn {i} " + ("x" * 3000)}
        for i in range(80)
    ]
    context = {
        "messages": huge_messages,
        "prefetched_restaurant_list": [{"id": "r1", "name": "x" * 5000}],
        "prefetched_menu": {"items": list(range(500))},
        "last_food_search": [{"name": f"item-{i}"} for i in range(50)],
        "suggested_items": [{"idx": i, "menu_item_id": f"id-{i}"} for i in range(100)],
        "greeting_sent": True,
    }
    compact = prepare_context_for_storage(context)
    assert "prefetched_restaurant_list" not in compact
    assert "prefetched_menu" not in compact
    assert len(compact["messages"]) <= 16
    assert all(len(str(m.get("content") or "")) <= 1500 for m in compact["messages"])
    assert len(compact["last_food_search"]) <= 12
    assert len(compact["suggested_items"]) <= 24
    payload = __import__("json").dumps(compact, ensure_ascii=False).encode("utf-8")
    assert len(payload) < 52_000


def test_fit_context_json_size_shrinks_oversized_payload():
    context = {
        "greeting_sent": True,
        "messages": [{"role": "user", "content": "y" * 40_000}],
    }
    fitted = fit_context_json_size(context, max_bytes=8_000)
    assert len(__import__("json").dumps(fitted, ensure_ascii=False).encode("utf-8")) <= 8_000

