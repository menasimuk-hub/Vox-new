from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.custom_org_profile_service import (
    CustomOrgProfileError,
    CustomOrgProfileService,
)

router = APIRouter(prefix="/admin/custom-org-profiles", tags=["admin-custom-org-profiles"])


@router.get("")
def list_custom_org_profiles(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {
        "ok": True,
        "profiles": CustomOrgProfileService.list_profiles(db),
        "options": CustomOrgProfileService.options(db),
    }


@router.get("/{profile_id}")
def get_custom_org_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = CustomOrgProfileService.get_profile(db, profile_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return {"ok": True, "profile": row, "options": CustomOrgProfileService.options(db)}


@router.post("")
def create_custom_org_profile(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return {"ok": True, "profile": CustomOrgProfileService.create_profile(db, payload or {})}
    except CustomOrgProfileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/{profile_id}")
def update_custom_org_profile(
    profile_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return {"ok": True, "profile": CustomOrgProfileService.update_profile(db, profile_id, payload or {})}
    except CustomOrgProfileError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) == "Profile not found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete("/{profile_id}")
def delete_custom_org_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        CustomOrgProfileService.delete_profile(db, profile_id)
    except CustomOrgProfileError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}
