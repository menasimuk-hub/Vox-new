"""Tests for SmartPipeline single-LLM waiter brain."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.abuu.agent.session import Session as AgentSession, load_session, save_session
from app.abuu.services.seed_service import AbuuSeedService
from app.abuu.waiter.deepseek_client import DeepSeekResult
from app.abuu.waiter.smart_pipeline import (
    SmartPipeline,
    _normalize_selection,
    _parse_ai_response,
    _refresh_restaurant_index,
)
from app.abuu.services.restaurant_discovery_service import rank_restaurants


@pytest.fixture
def abuu_seeded(app_client):
    from sqlalchemy import select

    from app.abuu.models.entities import Restaurant
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        db.commit()
        restaurant = db.execute(select(Restaurant).where(Restaurant.id == "abuu-rest-chicken")).scalar_one()
        yield db, restaurant.id, restaurant


@pytest.fixture
def main_db():
    return MagicMock()


def test_normalize_selection_arabic_numeral():
    assert _normalize_selection("١") == "1"


def test_parse_ai_response_json():
    raw = '{"reply":"أهلاً","action":"select_restaurant","restaurant_id":"abuu-rest-chicken","item_id":null,"order_confirmed":false}'
    parsed = _parse_ai_response(raw)
    assert parsed.action == "select_restaurant"
    assert parsed.restaurant_id == "abuu-rest-chicken"
    assert parsed.reply == "أهلاً"


def test_parse_ai_response_invalid_fallback():
    parsed = _parse_ai_response("مرحبا")
    assert parsed.reply == "مرحبا"
    assert parsed.action == "none"


@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_restaurant_pick_by_number(mock_complete, abuu_seeded, main_db):
    abuu_db, chicken_id, _restaurant = abuu_seeded
    phone = "+972509999001"

    ranked = rank_restaurants(abuu_db, lat=None, lng=None, limit=15)
    session = load_session(abuu_db, phone)
    _refresh_restaurant_index(session, ranked)
    save_session(abuu_db, session)

    mock_complete.return_value = DeepSeekResult(text="", fallback_used=True)

    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text="1")
    abuu_db.commit()

    assert result["handled"] is True
    assert result["action"] == "select_restaurant"
    assert result["restaurant_id"] is not None
    assert "كيف بقدر أساعدك" not in (result.get("reply") or "")
    assert result["restaurant_id"] == ranked[0].restaurant.id

    session2 = load_session(abuu_db, phone)
    assert session2.restaurant_id == ranked[0].restaurant.id


@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_restaurant_pick_arabic_numeral(mock_complete, abuu_seeded, main_db):
    abuu_db, _chicken_id, _restaurant = abuu_seeded
    phone = "+972509999002"
    ranked = rank_restaurants(abuu_db, lat=None, lng=None, limit=15)
    session = load_session(abuu_db, phone)
    _refresh_restaurant_index(session, ranked)
    save_session(abuu_db, session)

    mock_complete.return_value = DeepSeekResult(text="", fallback_used=True)
    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text="١")

    assert result["action"] == "select_restaurant"
    assert "كيف بقدر أساعدك" not in (result.get("reply") or "")


@patch("app.abuu.waiter.smart_pipeline.expand_food_query")
@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_chicken_search_after_restaurant_bound(mock_complete, mock_expand, abuu_seeded, main_db):
    abuu_db, chicken_id, _restaurant = abuu_seeded
    phone = "+972509999003"

    from app.abuu.menu_intelligence.query_expansion import QueryExpansionResult

    mock_expand.return_value = QueryExpansionResult(
        raw="بدي دجاج",
        synonym_text="دجاج",
        expanded="دجاج",
        unknown=False,
        ai_used=False,
        ai_failed=False,
    )
    mock_complete.return_value = DeepSeekResult(
        text=json.dumps(
            {
                "reply": "هاي أحلى 10 دجاج:\n1. شاورما — 35 ₪",
                "action": "show_menu",
                "restaurant_id": None,
                "item_id": None,
                "order_confirmed": False,
            },
            ensure_ascii=False,
        ),
        fallback_used=False,
    )

    session = load_session(abuu_db, phone)
    session.restaurant_id = chicken_id
    session.context = dict(session.context or {})
    session.context["restaurant_id"] = chicken_id
    session.context["restaurant_selected"] = True
    save_session(abuu_db, session)

    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text="بدي دجاج")
    assert result["handled"] is True
    assert "كيف بقدر أساعدك" not in (result.get("reply") or "")
    mock_complete.assert_called_once()


@patch("app.abuu.waiter.smart_pipeline.expand_food_query")
@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_refinement_merges_search(mock_complete, mock_expand, abuu_seeded, main_db):
    abuu_db, chicken_id, _restaurant = abuu_seeded
    phone = "+972509999004"

    from app.abuu.menu_intelligence.query_expansion import QueryExpansionResult

    mock_expand.return_value = QueryExpansionResult(
        raw="دجاج هندي",
        synonym_text="دجاج هندي",
        expanded="دجاج هندي",
        unknown=False,
        ai_used=False,
        ai_failed=False,
    )
    mock_complete.return_value = DeepSeekResult(
        text=json.dumps(
            {
                "reply": "تمام، دجاج هندي 👌",
                "action": "show_menu",
                "restaurant_id": None,
                "item_id": None,
                "order_confirmed": False,
            },
            ensure_ascii=False,
        ),
        fallback_used=False,
    )

    session = load_session(abuu_db, phone)
    session.restaurant_id = chicken_id
    session.context = {
        "restaurant_id": chicken_id,
        "restaurant_selected": True,
        "last_food_search": {"raw": "بدي دجاج", "expanded": "دجاج", "item_ids": [], "shown_count": 10},
    }
    save_session(abuu_db, session)

    SmartPipeline.handle(abuu_db, main_db, phone=phone, text="لا بدي دجاج هندي")
    assert mock_expand.called
    call_raw = mock_expand.call_args.kwargs.get("raw") or mock_expand.call_args[1].get("raw")
    if call_raw is None:
        call_raw = mock_expand.call_args[0][1] if len(mock_expand.call_args[0]) > 1 else mock_expand.call_args[0][0]
    assert "هندي" in str(call_raw)


@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_confirm_order_delegates(mock_complete, abuu_seeded, main_db):
    abuu_db, chicken_id, _restaurant = abuu_seeded
    phone = "+972509999005"

    mock_complete.return_value = DeepSeekResult(
        text=json.dumps(
            {
                "reply": "تمام نأكد!",
                "action": "confirm_order",
                "restaurant_id": None,
                "item_id": None,
                "order_confirmed": True,
            },
            ensure_ascii=False,
        ),
        fallback_used=False,
    )

    session = load_session(abuu_db, phone)
    session.restaurant_id = chicken_id
    session.context = {"restaurant_id": chicken_id, "restaurant_selected": True}
    session.cart = [{"name": "شاورما", "quantity": 1, "price": 35.0}]
    save_session(abuu_db, session)

    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text="أكد")
    assert result["action"] == "delegate_confirm"


@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_invalid_json_fallback(mock_complete, abuu_seeded, main_db):
    abuu_db, chicken_id, _restaurant = abuu_seeded
    phone = "+972509999006"

    mock_complete.return_value = DeepSeekResult(text="not json at all", fallback_used=False)

    session = load_session(abuu_db, phone)
    session.restaurant_id = chicken_id
    session.context = {"restaurant_id": chicken_id, "restaurant_selected": True}
    save_session(abuu_db, session)

    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text="بدي دجاج")
    assert result["handled"] is True
    assert result.get("reply")


@patch("app.abuu.waiter.pipeline.SmartPipeline.handle")
def test_pipeline_guard_routes_to_smart(mock_smart, abuu_seeded, main_db):
    abuu_db, _rid, _rest = abuu_seeded
    mock_smart.return_value = {"handled": True, "action": "none", "reply": "ok"}
    phone = "+972509999007"

    with patch.dict(os.environ, {"SMART_PIPELINE_ENABLED": "true"}):
        from app.abuu.waiter.pipeline import WaiterPipeline

        WaiterPipeline.handle(abuu_db, main_db, phone=phone, text="1")

    mock_smart.assert_called_once()


@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_restaurant_name_direct_pick(mock_complete, abuu_seeded, main_db):
    abuu_db, chicken_id, restaurant = abuu_seeded
    phone = "+972509999008"
    ranked = rank_restaurants(abuu_db, lat=None, lng=None, limit=15)

    session = load_session(abuu_db, phone)
    _refresh_restaurant_index(session, ranked)
    session.context["awaiting_restaurant_pick"] = True
    save_session(abuu_db, session)

    mock_complete.return_value = DeepSeekResult(text="", fallback_used=True)
    name = restaurant.name_ar or restaurant.name_en
    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text=name)

    assert result["action"] == "select_restaurant"
    assert result["restaurant_id"] == chicken_id
