"""Dedicated Abuu Telnyx webhook (future dedicated WA number)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.abuu.services.inbound_service import AbuuInboundService
from app.core.database import get_db
from app.services.telnyx_inbound_messaging_service import _extract_message_text, _phone_from

router = APIRouter(prefix="/abuu/webhooks", tags=["abuu-webhooks"])


@router.post("/inbound")
async def abuu_inbound_webhook(request: Request, db: Session = Depends(get_db)):
    payload: dict[str, Any] = await request.json()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    record = data.get("payload") if isinstance(data.get("payload"), dict) else data
    from_phone = _phone_from(record.get("from"))
    body = _extract_message_text(record)
    message_id = str(record.get("id") or record.get("message_id") or "").strip() or None
    result = AbuuInboundService.try_handle(
        db,
        from_phone=from_phone,
        body=body,
        message_id=message_id,
        record=record,
    )
    return {"ok": True, "abuu": result}
