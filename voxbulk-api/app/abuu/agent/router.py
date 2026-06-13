"""HTTP routes for Abuu conversational agent."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.agent.session import clear_session, load_session
from app.abuu.models.entities import CustomerOrder
from app.abuu.services.inbound_service import AbuuInboundService
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.serializers import order_to_dict
from app.core.abuu_database import get_abuu_db
from app.core.config import get_settings
from app.core.database import get_db
from app.services.telnyx_inbound_messaging_service import _extract_message_text, _phone_from

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/abuu", tags=["abuu-agent"])


def _verify_webhook_secret(request: Request, body: bytes) -> None:
    settings = get_settings()
    secret = (settings.abuu_webhook_secret or "").strip()
    if not secret:
        return
    signature = request.headers.get("X-Abuu-Signature") or request.headers.get("X-Hub-Signature-256") or ""
    if signature.startswith("sha256="):
        signature = signature[7:]
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def _verify_internal_key(x_abuu_internal_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = (settings.abuu_agent_internal_key or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Internal agent API not configured")
    if not x_abuu_internal_key or not hmac.compare_digest(x_abuu_internal_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/webhook")
async def abuu_agent_webhook(request: Request, main_db: Session = Depends(get_db)):
    body = await request.body()
    _verify_webhook_secret(request, body)
    payload: dict[str, Any] = json.loads(body.decode("utf-8") if body else "{}")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    record = data.get("payload") if isinstance(data.get("payload"), dict) else data
    from_phone = _phone_from(record.get("from"))
    body_text = _extract_message_text(record)
    message_id = str(record.get("id") or record.get("message_id") or "").strip() or None
    result = AbuuInboundService.try_handle(
        main_db,
        from_phone=from_phone,
        body=body_text,
        message_id=message_id,
        record=record,
    )
    return {"ok": True, "abuu": result}


@router.get("/order/{order_id}/status")
def abuu_order_status(
    order_id: str,
    abuu_db: Session = Depends(get_abuu_db),
    x_customer_phone: str | None = Header(default=None, alias="X-Customer-Phone"),
    _: None = Depends(_verify_internal_key),
):
    order = abuu_db.get(CustomerOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if x_customer_phone:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, x_customer_phone)
        if order.customer_id != customer.id:
            raise HTTPException(status_code=403, detail="Forbidden")
    return {"ok": True, "order": order_to_dict(order)}


@router.post("/session/{customer_wa_number}/reset")
def abuu_session_reset(
    customer_wa_number: str,
    abuu_db: Session = Depends(get_abuu_db),
    _: None = Depends(_verify_internal_key),
):
    session = load_session(abuu_db, customer_wa_number)
    order = None
    if session.active_order_id:
        order = abuu_db.get(CustomerOrder, session.active_order_id)
    if order is not None and order.status == "draft":
        AbuuOrderDraftService.cancel_draft(abuu_db, order)
    clear_session(abuu_db, customer_wa_number)
    abuu_db.commit()
    return {"ok": True, "cleared": True}
