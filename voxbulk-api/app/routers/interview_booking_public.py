"""Public interview booking — no authentication required."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
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


@router.post("/{token}/confirm")
def confirm_booking(token: str, payload: dict, db: Session = Depends(get_db)):
    slot = payload.get("slot_start_at") or payload.get("slot_start")
    if not slot:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slot_start_at is required")
    try:
        return InterviewBookingService.confirm_booking(db, token, str(slot))
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
