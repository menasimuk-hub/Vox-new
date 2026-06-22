"""Public Telnyx webhook endpoints for live appointment assistant tools."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.appointment_tool_service import (
    build_initialization_response,
    dispatch_appointment_tool,
)
from app.services.telnyx_webhook_security import TelnyxWebhookVerificationError, verify_telnyx_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appointments/telnyx-tools", tags=["appointment-telnyx-tools"])


async def _verified_json(request: Request) -> dict:
    raw_body = await request.body()
    try:
        verify_telnyx_webhook(
            raw_body,
            signature_header=request.headers.get("telnyx-signature-ed25519"),
            timestamp_header=request.headers.get("telnyx-timestamp"),
        )
    except TelnyxWebhookVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body") from exc
    return payload if isinstance(payload, dict) else {}


@router.get("/initialization")
@router.head("/initialization")
async def telnyx_initialization_probe():
    return {"ok": True, "endpoint": "appointment_telnyx_initialization"}


@router.post("/initialization")
async def telnyx_initialization(request: Request, db: Session = Depends(get_db)):
    """Telnyx dynamic-variables webhook (assistant.initialization)."""
    payload = await _verified_json(request)
    return build_initialization_response(db, payload)


@router.get("/{tool_name}")
@router.head("/{tool_name}")
async def telnyx_tool_probe(tool_name: str):
    return {"ok": True, "tool": tool_name}


@router.post("/{tool_name}")
async def telnyx_tool(tool_name: str, request: Request, db: Session = Depends(get_db)):
    """Telnyx webhook tool handler (check_availability, reschedule, cancel, confirm)."""
    payload = await _verified_json(request)
    try:
        return dispatch_appointment_tool(db, tool_name, payload)
    except Exception as exc:
        logger.exception("appointment_telnyx_tool_failed tool=%s", tool_name)
        raise HTTPException(status_code=500, detail=str(exc)[:200]) from exc
