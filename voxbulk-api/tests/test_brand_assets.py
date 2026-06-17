from __future__ import annotations

from pathlib import Path

import pytest

from app.services.brand_assets import asset_path, list_available_assets


def test_ya_brand_asset_on_disk():
    path = asset_path("ya")
    if path is None:
        pytest.skip("voxbulk-api/logos/ya.jpg not present in this checkout")
    assert path.name == "ya.jpg"
    assert path.is_file()


def test_ya_listed_when_present():
    path = Path(__file__).resolve().parents[1] / "logos" / "ya.jpg"
    if not path.is_file():
        pytest.skip("voxbulk-api/logos/ya.jpg not present in this checkout")
    available = list_available_assets()
    assert available.get("ya") == "ya.jpg"


def test_brand_ya_endpoint(app_client):
    path = Path(__file__).resolve().parents[1] / "logos" / "ya.jpg"
    if not path.is_file():
        pytest.skip("voxbulk-api/logos/ya.jpg not present in this checkout")
    res = app_client.get("/public/brand/ya")
    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("image/")
