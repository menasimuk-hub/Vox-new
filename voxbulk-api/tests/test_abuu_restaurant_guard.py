"""Tests for restaurant guard — single cart, no silent restaurant switch."""

from __future__ import annotations

import pytest

from app.abuu.conversation.restaurant_guard import (
    RestaurantGuard,
    RestaurantMismatchError,
    bind_restaurant_context,
    clear_switch_context,
    cross_restaurant_message,
    order_is_bound,
)
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
        db.commit()
        restaurants = list(db.execute(select(Restaurant).limit(5)).scalars().all())
        yield db, restaurants


def test_order_is_bound_with_selected_flag_empty_cart(abuu_seeded):
    db, restaurants = abuu_seeded
    customer = AbuuOrderDraftService.get_or_create_customer(db, "+972509991101")
    order = AbuuOrderDraftService.start_draft(db, customer=customer, restaurant=restaurants[0])
    ctx = bind_restaurant_context({}, restaurants[0].id)
    assert order_is_bound(order, ctx) is True


def test_ensure_order_blocks_silent_switch_when_selected_empty_cart(abuu_seeded):
    db, restaurants = abuu_seeded
    if len(restaurants) < 2:
        pytest.skip("need 2 restaurants")

    customer = AbuuOrderDraftService.get_or_create_customer(db, "+972509991102")
    rest_a, rest_b = restaurants[0], restaurants[1]
    order = AbuuOrderDraftService.start_draft(db, customer=customer, restaurant=rest_a)
    ctx = bind_restaurant_context({}, rest_a.id)

    with pytest.raises(RestaurantMismatchError):
        AbuuOrderDraftService.ensure_order(
            db,
            customer=customer,
            restaurant=rest_b,
            existing_order=order,
            context=ctx,
        )


def test_clear_switch_context_removes_stale_keys():
    ctx = clear_switch_context(
        {
            "pending_restaurant_switch": {"x": 1},
            "suggested_items": [1],
            "last_food_search": [2],
            "restaurant_id": "r1",
        }
    )
    assert "pending_restaurant_switch" not in ctx
    assert "suggested_items" not in ctx
    assert ctx["restaurant_id"] == "r1"


def test_cross_restaurant_message_mentions_fee(abuu_seeded):
    db, restaurants = abuu_seeded
    if len(restaurants) < 2:
        pytest.skip("need 2 restaurants")
    msg = cross_restaurant_message(
        db,
        lang="ar",
        current_restaurant=restaurants[0],
        target_restaurant=restaurants[1],
        target_item_name="شاورما",
    )
    assert "15" in msg or "₪" in msg
    assert "شاورما" in msg


def test_guard_blocks_cross_restaurant_add(abuu_seeded):
    db, restaurants = abuu_seeded
    if len(restaurants) < 2:
        pytest.skip("need 2 restaurants")

    phone = "+972509991103"
    customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
    rest_a, rest_b = restaurants[0], restaurants[1]
    order = AbuuOrderDraftService.start_draft(db, customer=customer, restaurant=rest_a)
    items_a = AbuuOrderDraftService.list_menu_items(db, rest_a.id, limit=1)
    items_b = AbuuOrderDraftService.list_menu_items(db, rest_b.id, limit=1)
    assert items_a and items_b
    order = AbuuOrderDraftService.add_item(db, order, items_a[0])

    guard = RestaurantGuard.try_add_item(
        db,
        customer=customer,
        order=order,
        context={"restaurant_id": rest_a.id, "restaurant_selected": True},
        item=items_b[0],
        restaurant=rest_b,
        lang="ar",
    )
    assert not guard.ok
    assert guard.action == "cross_restaurant_blocked"
