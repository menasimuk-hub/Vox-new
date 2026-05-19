from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.services.notification_service import NotificationService, notification_to_dict


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_my_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    rows = NotificationService.list_user_notifications(
        db,
        org_id=principal.org_id,
        user_id=principal.user_id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )
    return [notification_to_dict(row) for row in rows]


@router.get("/unread-count")
def my_unread_notification_count(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    return {"count": NotificationService.unread_count(db, org_id=principal.org_id, user_id=principal.user_id)}


@router.post("/{notification_id}/read")
def mark_my_notification_read(notification_id: int, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    row = NotificationService.mark_read(
        db,
        org_id=principal.org_id,
        user_id=principal.user_id,
        notification_id=notification_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification_to_dict(row)
