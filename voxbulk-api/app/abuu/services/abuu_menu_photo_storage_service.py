"""On-disk storage for Abuu menu item photos."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.core.config import get_settings

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_BYTES = 2 * 1024 * 1024


class MenuPhotoStorageError(Exception):
    pass


def _api_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_storage_root() -> Path:
    settings = get_settings()
    configured = getattr(settings, "abuu_menu_photo_dir", "") or os.environ.get("ABUU_MENU_PHOTO_DIR", "")
    if configured:
        root = Path(configured)
        if not root.is_absolute():
            root = (_api_root().parent / configured).resolve()
    else:
        root = (_api_root() / "data" / "abuu_menu_photos").resolve()
    return root


def check_storage_ready() -> dict:
    root = resolve_storage_root()
    exists = root.exists()
    writable = False
    error = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
    except OSError as exc:
        error = str(exc)
    return {
        "path": str(root),
        "exists": exists,
        "writable": writable,
        "error": error,
    }


def ensure_storage_ready() -> Path:
    status = check_storage_ready()
    if not status["writable"]:
        raise MenuPhotoStorageError(
            f"Menu photo directory not writable: {status['path']} ({status.get('error') or 'permission denied'})"
        )
    return Path(status["path"])


def _base_dir() -> Path:
    return ensure_storage_ready()


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
    try:
        path.write_bytes(content)
    except OSError as exc:
        raise MenuPhotoStorageError(f"Failed to write menu photo to {path}: {exc}") from exc
    return storage_key


def resolve_photo_path(storage_key: str) -> Path | None:
    if not storage_key or ".." in storage_key.replace("\\", "/"):
        return None
    path = resolve_storage_root() / storage_key.replace("\\", "/")
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
    rel = f"/abuu/menu-photos/{storage_key.replace(chr(92), '/')}"
    settings = get_settings()
    base = str(getattr(settings, "abuu_public_api_base_url", "") or os.environ.get("ABUU_PUBLIC_API_BASE_URL", "")).rstrip("/")
    if base:
        return f"{base}{rel}"
    return rel
