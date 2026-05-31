from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.brand_assets import PUBLIC_ASSETS, asset_media_type, asset_path

router = APIRouter(prefix="/public/brand", tags=["brand"])


@router.get("")
def list_brand_assets():
    return {"assets": list(PUBLIC_ASSETS.keys())}


@router.get("/{name}")
def get_brand_asset(name: str):
    path = asset_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Brand asset not found")
    return FileResponse(path, media_type=asset_media_type(path))
