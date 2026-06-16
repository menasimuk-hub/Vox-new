"""Tests for AI + synonym food query expansion before menu search."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.abuu.agent.session import Session as AgentSession
from app.abuu.conversation.fact_bundle import FactBundleLoader
from app.abuu.conversation.intent_router import AbuuIntent
from app.abuu.menu_intelligence.query_expansion import (
    UNKNOWN_QUERY_REPLY_AR,
    apply_food_synonyms,
    expand_food_query,
    intent_with_expansion,
    resolve_search_query,
)
from app.abuu.menu_intelligence.search_service import MenuSearchService
from app.abuu.menu_intelligence.query import MenuQuery
from app.abuu.services.preference_service import match_food_categories
from app.abuu.services.seed_service import AbuuSeedService
from app.abuu.waiter.deepseek_client import DeepSeekResult


def test_apply_food_synonyms_jaj_to_djaj():
    assert apply_food_synonyms("جاج") == "دجاج"


def test_apply_food_synonyms_chicken():
    assert apply_food_synonyms("chicken") == "دجاج"


def test_apply_food_synonyms_shaw_token():
    assert apply_food_synonyms("شاور") == "شاورما"


def test_match_food_categories_after_synonyms():
    assert "chicken" in match_food_categories(apply_food_synonyms("جاج"))


@patch("app.abuu.waiter.deepseek_client.WaiterDeepSeekClient.complete")
def test_expand_food_query_shaw_ma(mock_complete):
    mock_complete.return_value = DeepSeekResult(text="شاورما", fallback_used=False)
    result = expand_food_query(MagicMock(), raw="شاور ما")
    assert result.expanded == "شاورما"
    assert result.unknown is False
    assert result.ai_used is True


@patch("app.abuu.waiter.deepseek_client.WaiterDeepSeekClient.complete")
def test_expand_food_query_unknown(mock_complete):
    mock_complete.return_value = DeepSeekResult(text="UNKNOWN", fallback_used=False)
    result = expand_food_query(MagicMock(), raw="بدي اكل")
    assert result.unknown is True


@patch("app.abuu.waiter.deepseek_client.WaiterDeepSeekClient.complete")
def test_expand_food_query_xyz_unknown(mock_complete):
    mock_complete.return_value = DeepSeekResult(text="UNKNOWN", fallback_used=False)
    result = expand_food_query(MagicMock(), raw="xyz123")
    assert result.unknown is True


@patch("app.abuu.waiter.deepseek_client.WaiterDeepSeekClient.complete")
def test_expand_food_query_ai_failure_falls_back(mock_complete):
    mock_complete.side_effect = TimeoutError("timeout")
    result = expand_food_query(MagicMock(), raw="جاج")
    assert result.ai_failed is True
    assert result.expanded == "دجاج"
    assert result.unknown is False


@patch("app.abuu.waiter.deepseek_client.WaiterDeepSeekClient.complete")
def test_expand_food_query_biteh(mock_complete):
    mock_complete.return_value = DeepSeekResult(text="بيتزا", fallback_used=False)
    result = expand_food_query(MagicMock(), raw="بيتزه")
    assert result.expanded == "بيتزا"


@patch("app.abuu.waiter.deepseek_client.WaiterDeepSeekClient.complete")
def test_intent_with_expansion_chicken(mock_complete):
    mock_complete.return_value = DeepSeekResult(text="دجاج", fallback_used=False)
    expansion = expand_food_query(MagicMock(), raw="chicken")
    intent = intent_with_expansion(AbuuIntent("food_search"), expansion)
    assert "chicken" in intent.categories
    assert intent.item_query == "دجاج"


def test_resolve_search_query_uses_cache():
    session = AgentSession(
        customer_wa_number="+972501234567",
        context={
            "last_query_expansion": {
                "raw": "جاج",
                "synonym_text": "دجاج",
                "expanded": "دجاج",
                "unknown": False,
                "ai_used": True,
                "ai_failed": False,
            }
        },
    )
    with patch("app.abuu.menu_intelligence.query_expansion.expand_food_query") as mock_expand:
        result = resolve_search_query(session, MagicMock(), raw="جاج")
        mock_expand.assert_not_called()
    assert result.expanded == "دجاج"


@pytest.fixture
def abuu_seeded(app_client):
    from sqlalchemy import select

    from app.abuu.models.entities import Restaurant
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        db.commit()
        restaurant = db.execute(select(Restaurant).limit(1)).scalar_one()
        yield db, restaurant.id, restaurant


def test_menu_search_synonyms_jaj_finds_chicken(abuu_seeded):
    db, _restaurant_id, _restaurant = abuu_seeded
    chicken_restaurant_id = "abuu-rest-chicken"
    query = MenuQuery.from_categories([], limit=12)
    query.text_query = "جاج"
    items = MenuSearchService.search(db, chicken_restaurant_id, query)
    assert items
    hay = " ".join(f"{i.name_ar} {i.name_en}" for i in items).lower()
    assert "دجاج" in hay or "chicken" in hay


@patch("app.abuu.waiter.deepseek_client.WaiterDeepSeekClient.complete")
def test_food_search_bundle_jaj_returns_items(mock_complete, abuu_seeded):
    mock_complete.return_value = DeepSeekResult(text="دجاج", fallback_used=False)
    db, _restaurant_id, _restaurant = abuu_seeded
    session = AgentSession(customer_wa_number="+972501234567", language="ar", context={})
    intent = AbuuIntent("food_search", item_query="جاج")
    bundle = FactBundleLoader._food_search(
        db,
        intent,
        session,
        customer=None,
        lang="ar",
        main_db=MagicMock(),
        query_text=None,
    )
    assert bundle.customer_lines
    assert bundle.customer_lines != [UNKNOWN_QUERY_REPLY_AR]


@patch("app.abuu.waiter.deepseek_client.WaiterDeepSeekClient.complete")
def test_food_search_unknown_returns_clarify(mock_complete, abuu_seeded):
    mock_complete.return_value = DeepSeekResult(text="UNKNOWN", fallback_used=False)
    db, _restaurant_id, _restaurant = abuu_seeded
    session = AgentSession(customer_wa_number="+972501234567", language="ar", context={})
    intent = AbuuIntent("food_search", item_query="بدي اكل")
    bundle = FactBundleLoader._food_search(
        db,
        intent,
        session,
        customer=None,
        lang="ar",
        main_db=MagicMock(),
        query_text=None,
    )
    assert bundle.customer_lines == [UNKNOWN_QUERY_REPLY_AR]
    assert not bundle.food_items
