"""Caps for multipart uploads (recipient CSV/XLSX and similar)."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings


def recipient_upload_max_bytes() -> int:
    settings = get_settings()
    mb = max(1, int(getattr(settings, "recipient_upload_max_mb", 5) or 5))
    return mb * 1024 * 1024


def recipient_upload_max_rows() -> int:
    settings = get_settings()
    return max(1, int(getattr(settings, "recipient_upload_max_rows", 10_000) or 10_000))


async def read_upload_capped(
    upload: UploadFile,
    *,
    max_bytes: int | None = None,
) -> bytes:
    """Read an UploadFile while rejecting payloads larger than max_bytes (HTTP 413)."""
    limit = int(max_bytes if max_bytes is not None else recipient_upload_max_bytes())
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large (max {max(1, limit // (1024 * 1024))} MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)
