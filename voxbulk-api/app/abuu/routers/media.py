from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.abuu.services.abuu_menu_photo_storage_service import media_type_for_key, resolve_photo_path

router = APIRouter(prefix="/abuu/menu-photos", tags=["abuu-media"])


@router.get("/{storage_key:path}")
def get_menu_photo(storage_key: str):
    path = resolve_photo_path(storage_key)
    if path is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(path, media_type=media_type_for_key(storage_key))
