from __future__ import annotations

from app.abuu.services.yallasay_menu_seed_service import _cat_id, _item_id, _offer_id


def test_yallasay_seed_ids_fit_mysql_varchar36():
    rid = "abuu-rest-chicken"
    assert len(_cat_id(rid, "fast-snacks")) == 36
    assert len(_item_id(rid, "crispy-chicken-burger")) == 36
    assert len(_offer_id(rid, "family-burger")) == 36

    long_rid = "abuu-rest-exp-15"
    assert len(_cat_id(long_rid, "soft-drinks")) == 36
    assert len(_item_id(long_rid, "chocolate-shake")) == 36
