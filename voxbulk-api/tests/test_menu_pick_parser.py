from __future__ import annotations

import pytest

from app.abuu.agent.menu_pick_parser import (
    is_menu_pick_message,
    parse_menu_pick_tokens,
    resolve_menu_picks_to_items,
)
from app.abuu.agent.usage_help import is_usage_help_request


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1", [(1, 1)]),
        ("1 2 9", [(1, 1), (2, 1), (9, 1)]),
        ("1*3", [(1, 3)]),
        ("1×3 3*2", [(1, 3), (3, 2)]),
        ("٢ ٣", [(2, 1), (3, 1)]),
    ],
)
def test_parse_menu_pick_tokens(text, expected):
    assert parse_menu_pick_tokens(text) == expected
    assert is_menu_pick_message(text)


@pytest.mark.parametrize(
    "text",
    ["help", "1 2 abc", "بدي دجاج", "help me order"],
)
def test_not_menu_pick(text):
    assert parse_menu_pick_tokens(text) is None
    assert not is_menu_pick_message(text)


def test_resolve_menu_picks():
    index = [
        {"index": 1, "id": "item-a"},
        {"index": 2, "id": "item-b"},
        {"index": 9, "id": "item-i"},
    ]
    items, invalid = resolve_menu_picks_to_items(index, [(1, 1), (2, 2), (9, 1)])
    assert invalid == []
    assert items == [
        {"menu_item_id": "item-a", "quantity": 1},
        {"menu_item_id": "item-b", "quantity": 2},
        {"menu_item_id": "item-i", "quantity": 1},
    ]


def test_resolve_invalid_index():
    index = [{"index": 1, "id": "item-a"}]
    items, invalid = resolve_menu_picks_to_items(index, [(1, 1), (99, 1)])
    assert invalid == [99]
    assert len(items) == 1


@pytest.mark.parametrize(
    "text,expected",
    [
        ("مساعده", True),
        ("مساعدة", True),
        ("help", True),
        ("help me", False),
        ("1 2 3", False),
    ],
)
def test_usage_help(text, expected):
    assert is_usage_help_request(text) is expected
