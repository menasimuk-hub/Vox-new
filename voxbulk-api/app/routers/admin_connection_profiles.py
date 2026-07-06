from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.connection.connection_profile_service import (
    ConnectionProfileError,
    ConnectionProfilesAdminService,
)
from app.services.connection.constants import ALL_SERVICE_CODES

router = APIRouter(prefix="/admin/connection-profiles", tags=["admin-connection-profiles"])


@router.get("")
def list_connection_profiles(
    channel: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {
        "profiles": ConnectionProfilesAdminService.list_profiles(db, channel=channel),
        "webhook_urls": ConnectionProfilesAdminService.webhook_urls(),
        "service_codes": list(ALL_SERVICE_CODES),
    }


@router.get("/{profile_id}")
def get_connection_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = ConnectionProfilesAdminService.get_profile(db, profile_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return row


@router.post("")
def create_connection_profile(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return ConnectionProfilesAdminService.create_profile(db, payload)
    except ConnectionProfileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/{profile_id}")
def update_connection_profile(
    profile_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return ConnectionProfilesAdminService.update_profile(db, profile_id, payload)
    except ConnectionProfileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{profile_id}")
def delete_connection_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        ConnectionProfilesAdminService.delete_profile(db, profile_id)
    except ConnectionProfileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/{profile_id}/test")
def test_connection_profile(
    profile_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    payload = payload or {}
    to_number = str(payload.get("to_number") or "").strip() or None
    try:
        return ConnectionProfilesAdminService.test_profile(db, profile_id, to_number=to_number)
    except ConnectionProfileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
