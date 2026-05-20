from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_principal
from app.schemas.whatsapp import WhatsAppLogCreate, WhatsAppLogOut
from app.services.messaging_log_service import LogService
from app.services.telnyx_messaging_service import TelnyxMessagingService

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
    prefer_whatsapp = payload.get("prefer_whatsapp", True)
    if not to_number or not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to_number and body are required")
    try:
        if prefer_whatsapp:
            result = TelnyxMessagingService.send_whatsapp(db, to_number=to_number, body=body)
        else:
            result = TelnyxMessagingService.send_sms(db, to_number=to_number, body=body)
        if not result.ok:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.detail or result.status)
        log = TelnyxMessagingService.log_outbound(
            db,
            org_id=principal.org_id,
            to_number=to_number,
            from_number=None,
            body=body,
            result=result,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True, "log": log, "channel": result.channel, "external_id": result.external_id}


@router.get("/{log_id}", response_model=WhatsAppLogOut)
def get_whatsapp_log(log_id: int, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    obj = LogService.get_whatsapp_log(db, principal.org_id, log_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp log not found")
    return obj
