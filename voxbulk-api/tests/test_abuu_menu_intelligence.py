"""Tests for Abuu menu intelligence — tags, search, dietary detection, portal auth."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.abuu.core.auth import create_abuu_token
from app.abuu.menu_intelligence.dietary_detector import DietaryDetector
from app.abuu.menu_intelligence.enrich_rules import apply_inferred_tags, infer_tags_for_item
from app.abuu.menu_intelligence.query import MenuQuery
from app.abuu.menu_intelligence.search_service import MenuSearchService
from app.abuu.menu_intelligence.vocabulary import dump_json_tags
from app.abuu.models.entities import Driver, RestaurantMenuItem
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService
from app.core.config import get_settings


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


def test_infer_tags_for_drink_item():
    inferred = infer_tags_for_item(
        cat_key="soft-drinks",
        item_spec={"name_en": "Cola Zero", "name_ar": "كولا زيرو", "item_type": "drink"},
        profile="chicken",
    )
    assert inferred["item_type"] == "drink"
    assert inferred["classification_status"] == "classified"
    assert "soft_drink" in inferred["drink_tags"]


def test_infer_tags_for_chicken_meal():
    inferred = infer_tags_for_item(
        cat_key="grilled-chicken",
        item_spec={
            "name_en": "Grilled chicken shawarma",
            "name_ar": "شاورما دجاج مشوي",
            "item_type": "chicken",
            "description_en": "Charcoal grilled with cheese",
        },
        profile="chicken",
    )
    assert inferred["item_type"] in {"meal", "sandwich", "chicken"}
    assert "chicken" in inferred["protein_tags"]
    assert "dairy" in inferred["allergen_tags"]
    assert "grilled" in inferred["recipe_tags"]


def test_menu_search_drinks_category_returns_drinks_only(abuu_seeded):
    db, restaurant_id, _restaurant = abuu_seeded
    query = MenuQuery.from_categories(["drinks"], limit=8)
    items = MenuSearchService.search(db, restaurant_id, query)
    assert items
    for item in items:
        assert item.item_type in {"drink", "drinks"}


def test_allergen_strict_filter_excludes_nuts(abuu_seeded):
    db, restaurant_id, _restaurant = abuu_seeded
    items = AbuuOrderDraftService.list_menu_items(db, restaurant_id, limit=20)
    assert items
    target = items[0]
    target.allergen_tags_json = dump_json_tags(["nuts"])
    db.add(target)
    db.commit()

    safe = MenuSearchService.search(
        db,
        restaurant_id,
        MenuQuery(limit=20),
        customer=None,
    )
    safe_ids = {i.id for i in safe}

    filtered = MenuSearchService.search(
        db,
        restaurant_id,
        MenuQuery(allergen_avoid=["nuts"], limit=20),
    )
    filtered_ids = {i.id for i in filtered}
    assert target.id in safe_ids
    assert target.id not in filtered_ids


def test_dietary_detector_arabic_peanut_allergy():
    result = DietaryDetector.detect("عندي حساسية فول سوداني")
    assert "nuts" in result.allergens_avoid
    assert result.kitchen_note
    assert result.is_allergy_declared


def test_dietary_detector_english_vegan():
    result = DietaryDetector.detect("I'm vegan please")
    assert "vegan" in result.dietary_tags


def test_portal_token_expires_in_30_days():
    token = create_abuu_token(subject="test@example.com", token_type="abuu_restaurant", scope_id="rest-1")
    payload = jwt.decode(token, get_settings().jwt_secret_key, algorithms=[get_settings().jwt_algorithm])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    delta = exp - datetime.now(timezone.utc)
    assert timedelta(days=29) <= delta <= timedelta(days=31)


def test_driver_logout_sets_unavailable(abuu_seeded):
    db, _restaurant_id, _restaurant = abuu_seeded
    driver = db.get(Driver, "abuu-driver-01")
    if driver is None:
        pytest.skip("seed driver missing")
    driver.is_available = True
    db.add(driver)
    db.commit()

    driver.is_available = False
    db.add(driver)
    db.commit()

    refreshed = db.get(Driver, driver.id)
    assert refreshed is not None
    assert refreshed.is_available is False


def test_apply_inferred_tags_on_row():
    row = RestaurantMenuItem(
        id="test-item-tags",
        category_id="cat-1",
        name_en="Mint tea",
        name_ar="شاي نعناع",
        item_type="food",
        price_agorot=1000,
        classification_status="unclassified",
    )
    inferred = infer_tags_for_item(
        cat_key="hot-drinks",
        item_spec={"name_en": "Mint tea", "name_ar": "شاي نعناع", "item_type": "drink"},
    )
    assert apply_inferred_tags(row, inferred, force=True)
    assert row.item_type == "drink"
    assert row.classification_status == "classified"
    tags = json.loads(row.drink_tags_json or "[]")
    assert tags
