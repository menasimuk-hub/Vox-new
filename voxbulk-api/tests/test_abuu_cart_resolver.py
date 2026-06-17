"""Tests for agent cart reference resolution."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.abuu.agent.cart_resolver import _normalize_ref, resolve_cart_add_target
from app.abuu.models.entities import RestaurantMenuItem


def test_normalize_ref_strips_spaces():
    assert _normalize_ref("  سلطة   عربية  ") == "سلطة عربية"


def test_menu_index_lookup_from_context():
    db = MagicMock()
    item = MagicMock()
    item.is_deleted = False
    db.get.return_value = item

    ctx = {"menu_item_index": [{"index": 23, "id": "abuu-item-chicken-s1"}]}
    result = resolve_cart_add_target(
        db,
        restaurant_id="abuu-rest-chicken",
        ref="23",
        session_context=ctx,
    )
    assert result is not None
    assert result[0] == "menu_item"
    db.get.assert_any_call(RestaurantMenuItem, "abuu-item-chicken-s1")


def test_unknown_ref_returns_none():
    db = MagicMock()
    db.get.return_value = None
    db.execute.return_value.scalars.return_value.all.return_value = []
    assert (
        resolve_cart_add_target(
            db,
            restaurant_id="abuu-rest-chicken",
            ref="not-a-real-item",
            session_context={},
        )
        is None
    )
