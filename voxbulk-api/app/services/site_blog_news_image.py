"""Compress marketing-site images to a fixed theme canvas (WebP)."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

# Match blog card aspect (4:3) used on the public journal.
THEME_WIDTH = 1200
THEME_HEIGHT = 900
WEBP_QUALITY = 78
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

_REPO_ROOT = Path(__file__).resolve().parents[2]
MEDIA_ROOT = _REPO_ROOT / "data" / "blog-news"
PUBLIC_MEDIA_PREFIX = "/frontpage/blog-news/media"


def ensure_media_root() -> Path:
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    return MEDIA_ROOT


def media_abs_path(filename: str) -> Path:
    safe = Path(filename).name
    return MEDIA_ROOT / safe


def public_url_for(filename: str) -> str:
    return f"{PUBLIC_MEDIA_PREFIX}/{Path(filename).name}"


def compress_to_theme_webp(raw: bytes) -> bytes:
    """Accept any image bytes; cover-crop to theme size; emit small WebP."""
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image processing is unavailable (Pillow not installed).",
        ) from exc

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read that image. Upload a common format (JPEG, PNG, WebP, GIF, etc.).",
        ) from exc

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        background = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    fitted = ImageOps.fit(
        img,
        (THEME_WIDTH, THEME_HEIGHT),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    out = io.BytesIO()
    fitted.save(out, format="WEBP", quality=WEBP_QUALITY, method=6)
    return out.getvalue()


async def save_uploaded_theme_image(upload: UploadFile) -> str:
    """Store compressed theme image; return public URL path."""
    raw = await upload.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty image upload.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB before compression).",
        )

    webp = compress_to_theme_webp(raw)
    ensure_media_root()
    filename = f"{uuid.uuid4().hex}.webp"
    path = media_abs_path(filename)
    path.write_bytes(webp)
    return public_url_for(filename)
