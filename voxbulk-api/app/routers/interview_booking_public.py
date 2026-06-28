"""Public interview booking — no authentication required."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.interview_booking_service import InterviewBookingService

router = APIRouter(prefix="/public/interview-booking", tags=["public-interview-booking"])


@router.get("/{token}")
def get_booking_page(token: str, db: Session = Depends(get_db)):
    try:
        return InterviewBookingService.public_page(db, token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/{token}/calendar.ics")
def download_booking_calendar(token: str, db: Session = Depends(get_db)):
    try:
        ics_body, filename = InterviewBookingService.calendar_ics_payload(db, token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return Response(
        content=ics_body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{token}/confirm")
def confirm_booking(token: str, payload: dict, db: Session = Depends(get_db)):
    slot = payload.get("slot_start_at") or payload.get("slot_start")
    if not slot:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slot_start_at is required")
    try:
        channel = payload.get("channel")
        return InterviewBookingService.confirm_booking(db, token, str(slot), channel=channel)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{token}/cancel")
def cancel_booking(token: str, db: Session = Depends(get_db)):
    try:
        return InterviewBookingService.cancel_booking(db, token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{token}/reschedule")
def reschedule_booking(token: str, payload: dict, db: Session = Depends(get_db)):
    slot = payload.get("slot_start_at") or payload.get("slot_start")
    if not slot:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slot_start_at is required")
    try:
        return InterviewBookingService.reschedule_booking(db, token, str(slot))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{token}/meeting/start")
def start_meeting(token: str, db: Session = Depends(get_db)):
    from app.services.interview_meeting_service import InterviewMeetingService

    try:
        return InterviewMeetingService.start_meeting(db, token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/{token}/meeting/complete")
def complete_meeting(token: str, payload: dict | None = None, db: Session = Depends(get_db)):
    from app.services.interview_meeting_service import InterviewMeetingService

    payload = payload or {}
    try:
        duration = payload.get("duration_seconds")
        provider_call_id = payload.get("provider_call_id") or payload.get("conversation_id")
        secs = int(duration) if duration is not None else None
        return InterviewMeetingService.complete_meeting(
            db,
            token,
            duration_seconds=secs,
            provider_call_id=str(provider_call_id or "").strip() or None,
        )
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
