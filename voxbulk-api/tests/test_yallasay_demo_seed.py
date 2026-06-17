from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.abuu.core.auth import authenticate_restaurant
from app.abuu.services.yallasay_demo_seed_service import (
    DEMO_DRIVERS,
    DEMO_PASSWORD,
    DEMO_RESTAURANTS,
    YallasayDemoSeedService,
)


@pytest.fixture
def demo_env():
    with patch.dict(os.environ, {"ABUU_DEMO_SHOWALL_ENABLED": "true"}, clear=False):
        from app.core.config import get_settings

        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


def test_yallasay_demo_seed_menu_has_recipes_and_nuts(app_client, demo_env):
    import json

    from app.abuu.models.entities import RestaurantMenuItem
    from app.abuu.services.yallasay_menu_seed_service import _item_id
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        YallasayDemoSeedService.seed_all(db)
        db.commit()
        sweets_id = _item_id("abuu-rest-sweets", "baklava-mix")
        burger_id = _item_id("abuu-rest-fastfood", "cheese-burger")
        baklava = db.get(RestaurantMenuItem, sweets_id)
        burger = db.get(RestaurantMenuItem, burger_id)

    assert baklava is not None
    assert burger is not None
    allergens = json.loads(baklava.allergen_tags_json or "[]")
    assert "nuts" in allergens
    assert "halal" not in json.loads(baklava.dietary_tags_json or "[]")
    recipe = json.loads(baklava.ingredients_json or "{}")
    assert recipe.get("ingredients_en")
    burger_allergens = json.loads(burger.allergen_tags_json or "[]")
    assert "dairy" in burger_allergens
    assert "gluten" in burger_allergens


def test_yallasay_demo_seed_idempotent(app_client, demo_env):
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        first = YallasayDemoSeedService.seed_all(db)
        db.commit()
        second = YallasayDemoSeedService.seed_all(db)
        db.commit()

    assert len(first["restaurant_accounts"]) == 7
    assert len(first["driver_accounts"]) == 3
    assert second["restaurants_upserted"] == 0
    assert second["drivers_upserted"] == 0

    with get_abuu_sessionmaker()() as db:
        restaurant = authenticate_restaurant(db, "res4@yallasay.com", DEMO_PASSWORD)
        assert restaurant is not None
        assert restaurant.id == "abuu-rest-fastfood"


def test_demo_showall_endpoints_guarded(app_client):
    res = app_client.get("/abuu/internal/demo/restaurants")
    assert res.status_code == 404

    res2 = app_client.get("/abuu/internal/demo/drivers")
    assert res2.status_code == 404


def test_demo_showall_endpoints_when_enabled(app_client, demo_env):
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        YallasayDemoSeedService.seed_all(db)
        db.commit()

    res = app_client.get("/abuu/internal/demo/restaurants")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 7
    emails = {row["login_email"] for row in body["restaurants"]}
    assert emails == {row["email"] for row in DEMO_RESTAURANTS}

    res2 = app_client.get("/abuu/internal/demo/drivers")
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["count"] == 3
    assert body2["drivers"][0]["queued_orders_count"] >= 0
