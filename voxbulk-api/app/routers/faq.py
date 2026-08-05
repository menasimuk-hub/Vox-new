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
def public_faq(search: str | None = None, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """Authenticated dashboard FAQ — surface=dashboard only (no frontend fallback)."""
    from app.services.platform_product_visibility_service import PlatformProductVisibilityService
    from app.services.support_content_seed_service import SupportContentSeedService

    SupportContentSeedService.ensure_defaults(db)
    user = db.get(User, principal.user_id)
    viewer_email = getattr(user, "email", None) if user else None
    surface = "dashboard"
    cats = FAQService.list_categories(db, surface=surface)
    items = FAQService.list_items(
        db,
        search=search,
        published_only=True,
        limit=200,
        viewer_email=viewer_email,
        apply_integration_release_gate=True,
        surface=surface,
    )
    cat_slug_by_id = {int(c.id): str(c.slug or "") for c in cats if c.id is not None}
    visible_items = [
        i
        for i in items
        if PlatformProductVisibilityService.is_faq_visible(
            db,
            category_slug=cat_slug_by_id.get(int(i.category_id), None) if i.category_id else None,
            linked_service=getattr(i, "linked_service", None),
        )
    ]
    grouped = []
    for c in cats:
        rows = [item_to_dict(db, i) for i in visible_items if i.category_id == c.id]
        if rows:
            grouped.append({**category_to_dict(c), "items": rows})
    uncategorised = [item_to_dict(db, i) for i in visible_items if i.category_id is None]
    if uncategorised:
        grouped.append(
            {
                "id": None,
                "name": "Other",
                "slug": "other",
                "sort_order": 9999,
                "created_at": None,
                "surface": surface,
                "items": uncategorised,
            }
        )
    return grouped


@router.get("/admin/faq/categories")
def admin_faq_categories(surface: str | None = None, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    return [category_to_dict(c) for c in FAQService.list_categories(db, surface=surface)]


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
    surface: str | None = None,
    visible_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    from app.services.platform_product_visibility_service import PlatformProductVisibilityService
    from app.services.support_content_seed_service import SupportContentSeedService

    if surface == "dashboard" or visible_only:
        SupportContentSeedService.ensure_defaults(db)
    rows = FAQService.list_items(db, search=search, category_id=category_id, surface=surface, limit=limit, offset=offset)
    if visible_only:
        cats = {c.id: c for c in FAQService.list_categories(db, surface=surface)}
        rows = [
            i
            for i in rows
            if PlatformProductVisibilityService.is_faq_visible(
                db,
                category_slug=getattr(cats.get(i.category_id), "slug", None) if i.category_id else None,
                linked_service=getattr(i, "linked_service", None),
            )
        ]
    return [item_to_dict(db, i) for i in rows]


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
