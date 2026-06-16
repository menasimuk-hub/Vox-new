"""Tests for SmartPipeline single-LLM waiter brain."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.abuu.agent.session import Session as AgentSession, load_session, save_session
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService
from app.abuu.waiter.deepseek_client import DeepSeekResult
from app.abuu.waiter.smart_pipeline import (
    FORBIDDEN_REPLY_FRAGMENTS,
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


def assert_no_forbidden_reply(reply: str | None) -> None:
    text = str(reply or "")
    for fragment in FORBIDDEN_REPLY_FRAGMENTS:
        assert fragment not in text, f"forbidden fragment {fragment!r} in reply: {text!r}"


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
        from app.core.config import get_settings
        from app.abuu.waiter.pipeline import WaiterPipeline

        get_settings.cache_clear()
        try:
            WaiterPipeline.handle(abuu_db, main_db, phone=phone, text="1")
        finally:
            get_settings.cache_clear()

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


@patch("app.abuu.waiter.smart_pipeline.expand_food_query")
@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_djaj_without_restaurant_returns_items(mock_complete, mock_expand, abuu_seeded, main_db):
    """P0-1: Yallasay-style session — دجاج must not return empty/forbidden reply."""
    abuu_db, chicken_id, _restaurant = abuu_seeded
    phone = "+972509999009"

    from app.abuu.menu_intelligence.query_expansion import QueryExpansionResult

    mock_expand.return_value = QueryExpansionResult(
        raw="دجاج",
        synonym_text="دجاج",
        expanded="دجاج",
        unknown=False,
        ai_used=False,
        ai_failed=False,
    )
    mock_complete.return_value = DeepSeekResult(text="", fallback_used=True)

    session = load_session(abuu_db, phone)
    session.restaurant_id = None
    session.context = {"greeting_sent": True, "messages": []}
    save_session(abuu_db, session)

    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text="دجاج")
    assert result["handled"] is True
    assert_no_forbidden_reply(result.get("reply"))
    reply = result.get("reply") or ""
    assert "دجاج" in reply or "شاور" in reply or "المطاعم" in reply


def test_load_session_keeps_restaurant_after_start_context(abuu_seeded):
    """P1-1: restaurant_selected=True persists starter restaurant."""
    abuu_db, chicken_id, restaurant = abuu_seeded
    phone = "+972509999010"
    customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
    customer.name = "Qusay"
    abuu_db.add(customer)
    order = AbuuOrderDraftService.start_draft(abuu_db, customer=customer, restaurant=restaurant)
    AbuuOrderDraftService.upsert_session(
        abuu_db,
        phone=phone,
        step="awaiting_preference",
        context={
            "restaurant_id": chicken_id,
            "restaurant_selected": True,
            "greeting_sent": True,
        },
        active_order_id=order.id,
    )
    abuu_db.commit()
    session = load_session(abuu_db, phone)
    assert session.restaurant_id == chicken_id


@patch("app.abuu.waiter.smart_pipeline.expand_food_query")
@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_jaj_dialect_with_restaurant_bound(mock_complete, mock_expand, abuu_seeded, main_db):
    abuu_db, chicken_id, _restaurant = abuu_seeded
    phone = "+972509999011"

    from app.abuu.menu_intelligence.query_expansion import QueryExpansionResult

    mock_expand.return_value = QueryExpansionResult(
        raw="جاج",
        synonym_text="دجاج",
        expanded="دجاج",
        unknown=False,
        ai_used=False,
        ai_failed=False,
    )
    mock_complete.return_value = DeepSeekResult(text="", fallback_used=True)

    session = load_session(abuu_db, phone)
    session.restaurant_id = chicken_id
    session.context = {"restaurant_id": chicken_id, "restaurant_selected": True}
    save_session(abuu_db, session)

    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text="جاج")
    assert_no_forbidden_reply(result.get("reply"))
    assert result.get("reply")


@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_fake_item_id_not_added_to_cart(mock_complete, abuu_seeded, main_db):
    abuu_db, chicken_id, _restaurant = abuu_seeded
    phone = "+972509999012"

    mock_complete.return_value = DeepSeekResult(
        text=json.dumps(
            {
                "reply": "تمام!",
                "action": "add_to_cart",
                "restaurant_id": None,
                "item_id": "00000000-0000-0000-0000-000000000099",
                "order_confirmed": False,
            },
            ensure_ascii=False,
        ),
        fallback_used=False,
    )

    session = load_session(abuu_db, phone)
    session.restaurant_id = chicken_id
    session.context = {"restaurant_id": chicken_id, "restaurant_selected": True}
    session.cart = []
    save_session(abuu_db, session)

    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text="zzzznotadish")
    assert result["handled"] is True
    session2 = load_session(abuu_db, phone)
    assert not session2.cart


@patch("app.abuu.waiter.smart_pipeline.expand_food_query")
@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_empty_llm_falls_back_to_search_list(mock_complete, mock_expand, abuu_seeded, main_db):
    abuu_db, chicken_id, _restaurant = abuu_seeded
    phone = "+972509999013"

    from app.abuu.menu_intelligence.query_expansion import QueryExpansionResult

    mock_expand.return_value = QueryExpansionResult(
        raw="بدي دجاج",
        synonym_text="دجاج",
        expanded="دجاج",
        unknown=False,
        ai_used=False,
        ai_failed=False,
    )
    mock_complete.return_value = DeepSeekResult(text="", fallback_used=True)

    session = load_session(abuu_db, phone)
    session.restaurant_id = chicken_id
    session.context = {"restaurant_id": chicken_id, "restaurant_selected": True}
    save_session(abuu_db, session)

    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text="بدي دجاج")
    assert_no_forbidden_reply(result.get("reply"))
    assert "1." in (result.get("reply") or "")


@patch("app.abuu.waiter.smart_pipeline.WaiterDeepSeekClient.complete")
def test_dish_pick_by_number_after_menu_shown(mock_complete, abuu_seeded, main_db):
    abuu_db, chicken_id, _restaurant = abuu_seeded
    phone = "+972509999014"

    mock_complete.return_value = DeepSeekResult(text="", fallback_used=True)

    session = load_session(abuu_db, phone)
    session.restaurant_id = chicken_id
    session.context = {
        "restaurant_id": chicken_id,
        "restaurant_selected": True,
        "awaiting_dish_pick": True,
        "smart_menu_index": {"1": "abuu-item-chicken-1"},
    }
    save_session(abuu_db, session)

    result = SmartPipeline.handle(abuu_db, main_db, phone=phone, text="1")
    assert result["action"] in {"add_to_cart", "select_restaurant"}
    assert_no_forbidden_reply(result.get("reply"))


@patch("app.abuu.waiter.smart_pipeline.SmartPipeline.handle")
@patch("app.abuu.waiter.pipeline.WaiterIntentRouter.classify")
def test_smart_enabled_skips_intent_router(mock_classify, mock_smart, abuu_seeded, main_db):
    abuu_db, _rid, _rest = abuu_seeded
    mock_smart.return_value = {"handled": True, "action": "none", "reply": "ok"}
    phone = "+972509999015"

    with patch.dict(os.environ, {"SMART_PIPELINE_ENABLED": "true"}):
        from app.abuu.waiter.pipeline import WaiterPipeline

        WaiterPipeline.handle(abuu_db, main_db, phone=phone, text="دجاج")

    mock_classify.assert_not_called()
    mock_smart.assert_called_once()
