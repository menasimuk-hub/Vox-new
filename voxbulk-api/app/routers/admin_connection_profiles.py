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
from app.services.admin_org_service import AdminOrganisationService

router = APIRouter(prefix="/admin/connection-profiles", tags=["admin-connection-profiles"])


@router.get("")
def list_connection_profiles(
    channel: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    org_rows = AdminOrganisationService.list_orgs(db, limit=500, offset=0, search=None, zone=None)
    org_options = [{"id": o.id, "name": o.name or o.id} for o in org_rows]
    return {
        "profiles": ConnectionProfilesAdminService.list_profiles(db, channel=channel),
        "webhook_urls": ConnectionProfilesAdminService.webhook_urls(),
        "service_codes": list(ALL_SERVICE_CODES),
        "org_options": org_options,
    }


@router.get("/whatsapp-sync-options")
def whatsapp_sync_profile_options(
    service_code: str = Query(default="survey"),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.wa_template_sync_profile import list_whatsapp_sync_options

    items = list_whatsapp_sync_options(db, service_code=service_code)
    default_id = next((item["id"] for item in items if item.get("is_default")), None)
    if default_id is None and items:
        default_id = items[0]["id"]
    return {"ok": True, "items": items, "default_profile_id": default_id}


@router.get("/whatsapp-template-summaries")
def whatsapp_template_summaries_batch(
    profile_ids: str = Query(..., description="Comma-separated connection profile ids"),
    service_code: str = Query(default="survey"),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.wa_template_sync_profile import summarize_connection_profiles_batch

    ids = [part.strip() for part in str(profile_ids or "").split(",") if part.strip()]
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="profile_ids is required")
    if len(ids) > 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At most 10 profile ids per request")
    items = summarize_connection_profiles_batch(db, ids, service_code=service_code)
    return {"ok": True, "items": items}


@router.get("/{profile_id}/whatsapp-template-summary")
def whatsapp_template_summary_for_profile(
    profile_id: str,
    service_code: str = Query(default="survey"),
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.wa_template_sync_profile import summarize_for_connection_profile

    result = summarize_for_connection_profile(db, profile_id, service_code=service_code)
    if not result.get("ok"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(result.get("error") or "Could not load template summary for profile"),
        )
    return result


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
