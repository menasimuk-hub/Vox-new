from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.abuu.services.abuu_menu_photo_storage_service import (
    MenuPhotoStorageError,
    check_storage_ready,
    resolve_storage_root,
    save_photo_bytes,
)


def test_photo_storage_writable(tmp_path):
    with patch("app.abuu.services.abuu_menu_photo_storage_service.resolve_storage_root", return_value=tmp_path):
        status = check_storage_ready()
        assert status["writable"] is True
        key = save_photo_bytes(storage_key="rest/item/test.jpg", content=b"abc")
        assert key == "rest/item/test.jpg"
        assert (tmp_path / "rest/item/test.jpg").is_file()


def test_photo_storage_not_writable():
    with patch("app.abuu.services.abuu_menu_photo_storage_service.resolve_storage_root", return_value=Path("/Z:/nonexistent/abuu")):
        with patch("pathlib.Path.mkdir", side_effect=OSError("denied")):
            status = check_storage_ready()
            assert status["writable"] is False


def test_admin_upload_returns_503_on_storage_error(app_client):
    from app.core.abuu_database import get_abuu_sessionmaker, run_abuu_migrations
    from app.abuu.models.entities import RestaurantMenuCategory, RestaurantMenuItem
    from tests.test_abuu_crud import _mk_superadmin

    run_abuu_migrations()
    headers = _mk_superadmin(app_client)
    with get_abuu_sessionmaker()() as db:
        cat = db.execute(__import__("sqlalchemy").select(RestaurantMenuCategory).limit(1)).scalar_one()
        item = db.execute(
            __import__("sqlalchemy").select(RestaurantMenuItem).where(RestaurantMenuItem.category_id == cat.id).limit(1)
        ).scalar_one()
        item_id = item.id

    with patch(
        "app.abuu.services.abuu_menu_photo_storage_service.save_photo_bytes",
        side_effect=MenuPhotoStorageError("Menu photo directory not writable: /var/lib/voxbulk/abuu_menu_photos"),
    ):
        resp = app_client.post(
            f"/admin/abuu/menu-items/{item_id}/photo",
            headers=headers,
            files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        )
    assert resp.status_code == 503
    assert "not writable" in resp.json()["detail"].lower()
