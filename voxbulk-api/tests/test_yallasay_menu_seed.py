from __future__ import annotations

from app.abuu.services.yallasay_menu_catalog import (
    YALLASAY_PILOT_RESTAURANT_IDS,
    menu_for_profile,
    offers_for_profile,
    profile_for_restaurant,
)
from app.abuu.services.yallasay_menu_seed_service import _cat_id, _item_id, _offer_id


def test_yallasay_seed_ids_fit_mysql_varchar36():
    rid = "abuu-rest-chicken"
    assert len(_cat_id(rid, "fast-snacks")) == 36
    assert len(_item_id(rid, "crispy-chicken-burger")) == 36
    assert len(_offer_id(rid, "family-burger")) == 36

    long_rid = "abuu-rest-exp-15"
    assert len(_cat_id(long_rid, "soft-drinks")) == 36
    assert len(_item_id(long_rid, "chocolate-shake")) == 36


def test_pilot_restaurants_defined():
    assert len(YALLASAY_PILOT_RESTAURANT_IDS) == 7
    assert "abuu-rest-chicken" in YALLASAY_PILOT_RESTAURANT_IDS
    assert "abuu-rest-meat" in YALLASAY_PILOT_RESTAURANT_IDS
    assert "abuu-rest-shawarma" in YALLASAY_PILOT_RESTAURANT_IDS
    assert "abuu-rest-sweets" in YALLASAY_PILOT_RESTAURANT_IDS


def test_themed_menu_profiles_have_drinks():
    for profile in ("chicken", "meat", "fish", "fastfood", "vegan"):
        cats = menu_for_profile(profile)
        keys = {c["key"] for c in cats}
        assert "soft-drinks" in keys
        assert "juices" in keys
        offers = offers_for_profile(profile)
        assert len(offers) >= 2


def test_profile_for_sham_chicken():
    assert profile_for_restaurant("abuu-rest-chicken") == "chicken"
