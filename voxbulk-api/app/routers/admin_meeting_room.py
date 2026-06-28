"""Admin Meeting Room platform settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.services.meeting_room_settings_service import MeetingRoomSettingsService

router = APIRouter(prefix="/admin/meeting-room", tags=["admin-meeting-room"])


@router.get("/settings")
def get_meeting_room_settings(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return MeetingRoomSettingsService.get_settings(db)


@router.put("/settings")
def update_meeting_room_settings(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return MeetingRoomSettingsService.update_settings(
            db,
            agent_id=payload.get("agent_id"),
            language_code=payload.get("language_code"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/language-options")
def meeting_room_language_options(_admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"languages": MeetingRoomSettingsService.language_options()}
