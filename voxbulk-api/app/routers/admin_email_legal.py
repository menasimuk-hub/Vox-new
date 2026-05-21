from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_EMAIL, require_cap
from app.core.database import get_db
from app.schemas.legal_page import LegalPageOut, LegalPageUpdate
from app.services.legal_page_service import LegalPageService, legal_page_to_dict

router = APIRouter(prefix="/admin/email", tags=["admin-email-legal"])


@router.get("/legal-pages", response_model=list[LegalPageOut])
def admin_list_legal_pages(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    rows = LegalPageService.list_pages(db)
    return [LegalPageOut(**legal_page_to_dict(row)) for row in rows]


@router.get("/legal-pages/{slug}", response_model=LegalPageOut)
def admin_get_legal_page(slug: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    row = LegalPageService.get_page(db, slug)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal page not found")
    return LegalPageOut(**legal_page_to_dict(row))


@router.put("/legal-pages/{slug}", response_model=LegalPageOut)
def admin_update_legal_page(
    slug: str,
    payload: LegalPageUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    try:
        row = LegalPageService.update_page(
            db,
            slug,
            title=payload.title,
            meta_description=payload.meta_description,
            body=payload.body,
            is_published=payload.is_published,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return LegalPageOut(**legal_page_to_dict(row))
