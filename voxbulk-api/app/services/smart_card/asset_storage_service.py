"""Store Smart Card QR PDF/image uploads under data/smart-card-assets/{org_id}/."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

_REPO_ROOT = Path(__file__).resolve().parents[3]
SMART_CARD_ASSETS_ROOT = _REPO_ROOT / "data" / "smart-card-assets"

MAX_SMART_CARD_ASSET_BYTES = 20 * 1024 * 1024  # 20 MB
ALLOWED_EXTENSIONS = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".xls", ".xlsx", ".csv"}
)
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/gif",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
        "application/csv",
        "application/octet-stream",
    }
)


def ensure_smart_card_assets_root() -> Path:
    SMART_CARD_ASSETS_ROOT.mkdir(parents=True, exist_ok=True)
    return SMART_CARD_ASSETS_ROOT


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-._")
    return cleaned or "document.pdf"


def resolve_storage_abs_path(storage_path: str | None) -> Path | None:
    rel = str(storage_path or "").strip().replace("\\", "/")
    if not rel or ".." in rel.split("/"):
        return None
    abs_path = (_REPO_ROOT / rel).resolve()
    try:
        abs_path.relative_to(SMART_CARD_ASSETS_ROOT.resolve())
    except ValueError:
        return None
    return abs_path if abs_path.is_file() else None


async def save_smart_card_asset_upload(*, org_id: str, upload: UploadFile) -> dict:
    oid = str(org_id or "").strip()
    if not oid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organisation required")

    original = _safe_filename(upload.filename or "document.pdf")
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF, Excel, CSV, or image files are allowed (pdf, xls, xlsx, csv, png, jpg, webp, gif).",
        )

    content_type = str(upload.content_type or "").strip().lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES and not content_type.startswith("image/"):
        if content_type.startswith("text/") or content_type.startswith("audio/") or content_type.startswith("video/"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    raw = await upload.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(raw) > MAX_SMART_CARD_ASSET_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large (max 20 MB).",
        )

    ensure_smart_card_assets_root()
    org_dir = SMART_CARD_ASSETS_ROOT / oid
    org_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{original}"
    abs_path = org_dir / stored_name
    abs_path.write_bytes(raw)

    rel = abs_path.relative_to(_REPO_ROOT).as_posix()
    if ext == ".pdf":
        kind = "pdf"
    elif ext in {".xls", ".xlsx", ".csv"}:
        kind = "spreadsheet"
    else:
        kind = "image"
    return {
        "storage_path": rel,
        "original_filename": original,
        "size_bytes": len(raw),
        "kind": kind,
        "content_type": content_type or None,
    }
