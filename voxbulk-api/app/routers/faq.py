from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.models.user import User
from app.schemas.faq import FAQCategoryIn, FAQItemIn
from app.services.faq_service import FAQService, category_to_dict, item_to_dict

router = APIRouter(tags=["faq"])


@router.get("/faq")
def public_faq(search: str | None = None, db: Session = Depends(get_db), _principal=Depends(get_current_principal)):
    cats = FAQService.list_categories(db)
    items = FAQService.list_items(db, search=search, published_only=True, limit=200)
    grouped = []
    for c in cats:
        rows = [item_to_dict(db, i) for i in items if i.category_id == c.id]
        if rows:
            grouped.append({**category_to_dict(c), "items": rows})
    uncategorised = [item_to_dict(db, i) for i in items if i.category_id is None]
    if uncategorised:
        grouped.append({"id": None, "name": "Other", "slug": "other", "sort_order": 9999, "created_at": None, "items": uncategorised})
    return grouped


@router.get("/admin/faq/categories")
def admin_faq_categories(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return [category_to_dict(c) for c in FAQService.list_categories(db)]


@router.post("/admin/faq/categories")
def admin_create_faq_category(payload: FAQCategoryIn, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return category_to_dict(FAQService.upsert_category(db, category_id=None, **payload.model_dump()))


@router.put("/admin/faq/categories/{category_id}")
def admin_update_faq_category(category_id: int, payload: FAQCategoryIn, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return category_to_dict(FAQService.upsert_category(db, category_id=category_id, **payload.model_dump()))


@router.delete("/admin/faq/categories/{category_id}")
def admin_delete_faq_category(category_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    FAQService.delete_category(db, category_id)
    return {"ok": True}


@router.get("/admin/faq/items")
def admin_faq_items(
    search: str | None = None,
    category_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    return [item_to_dict(db, i) for i in FAQService.list_items(db, search=search, category_id=category_id, limit=limit, offset=offset)]


@router.post("/admin/faq/items")
def admin_create_faq_item(payload: FAQItemIn, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        row = FAQService.upsert_item(db, item_id=None, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return item_to_dict(db, row)


@router.put("/admin/faq/items/{item_id}")
def admin_update_faq_item(item_id: int, payload: FAQItemIn, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    try:
        row = FAQService.upsert_item(db, item_id=item_id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return item_to_dict(db, row)


@router.delete("/admin/faq/items/{item_id}")
def admin_delete_faq_item(item_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    FAQService.delete_item(db, item_id)
    return {"ok": True}

