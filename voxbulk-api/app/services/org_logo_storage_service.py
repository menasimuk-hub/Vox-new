"""On-disk storage for organisation brand logos."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.core.config import get_settings

# Stored formats after client WebP conversion (PNG/JPG still accepted for API clients).
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
REJECTED_EXTENSIONS = {".svg", ".gif", ".avif", ".bmp", ".ico"}
MAX_BYTES = 2 * 1024 * 1024

_FORMAT_ERROR = "Error: Only PNG and JPG images are supported"


def _base_dir() -> Path:
    settings = get_settings()
    configured = getattr(settings, "org_logo_storage_dir", "") or os.environ.get("ORG_LOGO_STORAGE_DIR", "")
    if configured:
        root = Path(configured)
    else:
        root = Path(__file__).resolve().parents[2] / "data" / "org_logos"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sniff_image_kind(content: bytes) -> str | None:
    """Return png|jpeg|webp|gif|svg|None from magic bytes."""
    if not content:
        return None
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if content[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    head = content[:256].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg"):
        return "svg"
    return None


def validate_logo_upload(*, filename: str, content: bytes) -> str:
    if not content:
        raise ValueError("Empty file")
    if len(content) > MAX_BYTES:
        raise ValueError("Logo must be 2 MB or smaller")

    ext = Path(filename or "logo.png").suffix.lower()
    if ext in REJECTED_EXTENSIONS:
        raise ValueError(_FORMAT_ERROR)

    kind = _sniff_image_kind(content)
    if kind in {"gif", "svg"}:
        raise ValueError(_FORMAT_ERROR)
    if kind == "png":
        return ".png"
    if kind == "jpeg":
        return ".jpg" if ext == ".jpg" else ".jpeg" if ext == ".jpeg" else ".jpg"
    if kind == "webp":
        # Allowed as *stored* format after browser Canvas conversion from PNG/JPG.
        return ".webp"
    if ext in ALLOWED_EXTENSIONS and kind is None:
        # Rare edge: truncated header — still reject unknown binary.
        raise ValueError(_FORMAT_ERROR)
    raise ValueError(_FORMAT_ERROR)


def normalize_logo_tone(value: str | None) -> str | None:
    v = str(value or "").strip().lower()
    if v in {"light", "dark"}:
        return v
    return None


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
    }.get(ext, "application/octet-stream")
