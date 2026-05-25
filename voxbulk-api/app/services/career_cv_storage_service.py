"""Private on-disk storage for interview CV attachments."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.core.config import settings

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


def _base_dir() -> Path:
    root = Path(getattr(settings, "cv_storage_dir", "") or os.environ.get("CV_STORAGE_DIR", "data/cv_intake"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def storage_key_for(*, org_id: str, order_id: str, filename: str) -> str:
    ext = Path(filename or "cv.bin").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".bin"
    token = uuid.uuid4().hex
    return f"{org_id}/{order_id}/{token}{ext}"


def save_cv_bytes(*, storage_key: str, content: bytes) -> str:
    path = _base_dir() / storage_key.replace("\\", "/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return storage_key


def resolve_cv_path(storage_key: str) -> Path | None:
    if not storage_key or ".." in storage_key.replace("\\", "/"):
        return None
    path = _base_dir() / storage_key.replace("\\", "/")
    if not path.is_file():
        return None
    return path


def delete_cv_file(storage_key: str | None) -> None:
    path = resolve_cv_path(str(storage_key or ""))
    if path and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
