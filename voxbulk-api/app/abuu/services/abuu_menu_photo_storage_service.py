"""On-disk storage for Abuu menu item photos."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.core.config import get_settings

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_BYTES = 2 * 1024 * 1024


def _base_dir() -> Path:
    settings = get_settings()
    configured = getattr(settings, "abuu_menu_photo_dir", "") or os.environ.get("ABUU_MENU_PHOTO_DIR", "")
    if configured:
        root = Path(configured)
    else:
        root = Path(__file__).resolve().parents[2] / "data" / "abuu_menu_photos"
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_menu_photo_upload(*, filename: str, content: bytes) -> str:
    if not content:
        raise ValueError("Empty file")
    if len(content) > MAX_BYTES:
        raise ValueError("Photo must be 2 MB or smaller")
    ext = Path(filename or "photo.jpg").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Photo must be PNG, JPG, or WEBP")
    return ext


def storage_key_for(*, restaurant_id: str, item_id: str, ext: str) -> str:
    token = uuid.uuid4().hex[:12]
    return f"{restaurant_id}/{item_id}/{token}{ext}"


def save_photo_bytes(*, storage_key: str, content: bytes) -> str:
    path = _base_dir() / storage_key.replace("\\", "/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return storage_key


def resolve_photo_path(storage_key: str) -> Path | None:
    if not storage_key or ".." in storage_key.replace("\\", "/"):
        return None
    path = _base_dir() / storage_key.replace("\\", "/")
    if not path.is_file():
        return None
    return path


def delete_photo_file(storage_key: str | None) -> None:
    path = resolve_photo_path(str(storage_key or ""))
    if path and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def media_type_for_key(storage_key: str) -> str:
    ext = Path(storage_key).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")


def photo_url_for(storage_key: str | None) -> str | None:
    if not storage_key:
        return None
    return f"/abuu/menu-photos/{storage_key.replace(chr(92), '/')}"
