from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.schemas.whatsapp import WhatsAppLogCreate, WhatsAppLogOut
from app.services.twilio_service import LogService, TwilioExecutionService

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

@router.get("", response_model=list[WhatsAppLogOut])
def list_whatsapp_logs(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    return LogService.list_whatsapp_logs(db, principal.org_id)


@router.post("", response_model=WhatsAppLogOut)
def create_whatsapp_log(payload: WhatsAppLogCreate, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    try:
        return LogService.create_whatsapp_log(db, principal.org_id, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/send")
def send_whatsapp_message(payload: dict, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    to_number = str(payload.get("to_number") or "").strip()
    body = str(payload.get("body") or "").strip()
    media_urls = payload.get("media_urls") or []
    if not to_number or not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to_number and body are required")
    if not isinstance(media_urls, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="media_urls must be a list")
    try:
        log = TwilioExecutionService.send_whatsapp(
            db,
            org_id=principal.org_id,
            to_number=to_number,
            body=body,
            appointment_id=(payload.get("appointment_id") or None),
            patient_id=(payload.get("patient_id") or None),
            media_urls=[str(x) for x in media_urls if str(x).strip()],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": log.status != "failed", "log": log}


@router.get("/{log_id}", response_model=WhatsAppLogOut)
def get_whatsapp_log(log_id: int, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    obj = LogService.get_whatsapp_log(db, principal.org_id, log_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp log not found")
    return obj

