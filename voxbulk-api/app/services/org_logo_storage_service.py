"""On-disk storage for organisation brand logos."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.core.config import get_settings

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
MAX_BYTES = 2 * 1024 * 1024


def _base_dir() -> Path:
    settings = get_settings()
    configured = getattr(settings, "org_logo_storage_dir", "") or os.environ.get("ORG_LOGO_STORAGE_DIR", "")
    if configured:
        root = Path(configured)
    else:
        root = Path(__file__).resolve().parents[2] / "data" / "org_logos"
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_logo_upload(*, filename: str, content: bytes) -> str:
    if not content:
        raise ValueError("Empty file")
    if len(content) > MAX_BYTES:
        raise ValueError("Logo must be 2 MB or smaller")
    ext = Path(filename or "logo.png").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Logo must be PNG, JPG, WEBP, or SVG")
    return ext


def storage_key_for(*, org_id: str, ext: str) -> str:
    token = uuid.uuid4().hex[:12]
    return f"{org_id}/{token}{ext}"


def save_logo_bytes(*, storage_key: str, content: bytes) -> str:
    path = _base_dir() / storage_key.replace("\\", "/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return storage_key


def resolve_logo_path(storage_key: str) -> Path | None:
    if not storage_key or ".." in storage_key.replace("\\", "/"):
        return None
    path = _base_dir() / storage_key.replace("\\", "/")
    if not path.is_file():
        return None
    return path


def delete_logo_file(storage_key: str | None) -> None:
    path = resolve_logo_path(str(storage_key or ""))
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
        ".svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")
