from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db
from app.services import site_blog_news_service as svc
from app.services.site_blog_news_image import (
    ensure_media_root,
    media_abs_path,
    save_uploaded_theme_image,
)

router = APIRouter(prefix="/frontpage", tags=["frontpage-blog-news"])
admin_router = APIRouter(prefix="/admin/blog-news", tags=["admin-blog-news"])


class ItemUpsert(BaseModel):
    kind: str | None = None
    title: str | None = None
    slug: str | None = None
    excerpt: str | None = None
    category: str | None = None
    author: str | None = None
    author_role: str | None = None
    image_url: str | None = None
    body_mode: str | None = None
    body: str | None = None
    published_at: str | None = None
    read_mins: int | None = None
    is_visible: bool | None = None
    sort_order: int | None = None


class ItemCreate(BaseModel):
    kind: str
    title: str
    slug: str | None = None
    excerpt: str = ""
    category: str | None = None
    author: str | None = None
    author_role: str | None = None
    image_url: str | None = None
    body_mode: str = "text"
    body: str = ""
    published_at: str | None = None
    read_mins: int = 3
    is_visible: bool = True
    sort_order: int = 0


# ---- Public ----


@router.get("/blog")
def public_list_blog(db: Session = Depends(get_db)):
    items = svc.list_items(db, kind=svc.KIND_BLOG, visible_only=True)
    return {"items": [svc.item_to_dict(r) for r in items]}


@router.get("/blog/{slug}")
def public_get_blog(slug: str, db: Session = Depends(get_db)):
    row = svc.get_by_slug(db, svc.KIND_BLOG, slug, visible_only=True)
    return svc.item_to_dict(row)


@router.get("/news")
def public_list_news(db: Session = Depends(get_db)):
    items = svc.list_items(db, kind=svc.KIND_NEWS, visible_only=True)
    return {"items": [svc.item_to_dict(r) for r in items]}


@router.get("/news/{slug}")
def public_get_news(slug: str, db: Session = Depends(get_db)):
    row = svc.get_by_slug(db, svc.KIND_NEWS, slug, visible_only=True)
    return svc.item_to_dict(row)


@router.get("/blog-news/media/{filename}")
def public_media(filename: str):
    ensure_media_root()
    path = media_abs_path(filename)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    return FileResponse(path, media_type="image/webp", filename=path.name)


# ---- Admin ----


@admin_router.get("")
def admin_list(
    kind: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    items = svc.list_items(db, kind=kind, visible_only=False)
    return {"items": [svc.item_to_dict(r, include_admin=True) for r in items]}


@admin_router.post("/upload-image")
async def admin_upload_image(
    file: UploadFile = File(...),
    _admin=Depends(require_platform_admin),
):
    url = await save_uploaded_theme_image(file)
    return {
        "image_url": url,
        "width": 1200,
        "height": 900,
        "format": "webp",
        "note": "Compressed and resized to theme canvas (1200×900 WebP).",
    }


@admin_router.get("/{item_id}")
def admin_get(item_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    return svc.item_to_dict(svc.get_by_id(db, item_id), include_admin=True)


@admin_router.post("", status_code=status.HTTP_201_CREATED)
def admin_create(
    body: ItemCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    row = svc.create_item(db, body.model_dump())
    return svc.item_to_dict(row, include_admin=True)


@admin_router.put("/{item_id}")
def admin_update(
    item_id: str,
    body: ItemUpsert,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    raw = body.model_dump(exclude_unset=True)
    row = svc.update_item(db, item_id, raw)
    return svc.item_to_dict(row, include_admin=True)


@admin_router.post("/{item_id}/toggle-visible")
def admin_toggle(
    item_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    row = svc.toggle_visible(db, item_id)
    return svc.item_to_dict(row, include_admin=True)


@admin_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete(
    item_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    svc.delete_item(db, item_id)
    return None
