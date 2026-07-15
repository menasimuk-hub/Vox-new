"""Public Telnyx webhook endpoints for live interview assistant tools."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.interview_telnyx_tool_service import (
    hangup_interview_call,
    mark_interview_session_signal,
)
from app.services.telnyx_webhook_security import TelnyxWebhookVerificationError, verify_telnyx_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interview/telnyx-tools", tags=["interview-telnyx-tools"])


async def _verified_json(request: Request, db: Session | None = None) -> dict:
    raw_body = await request.body()
    try:
        verify_telnyx_webhook(
            raw_body,
            signature_header=request.headers.get("telnyx-signature-ed25519"),
            timestamp_header=request.headers.get("telnyx-timestamp"),
            db=db,
        )
    except TelnyxWebhookVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body") from exc
    return payload if isinstance(payload, dict) else {}


@router.get("/end_call")
@router.head("/end_call")
@router.get("/mark_recording_consent")
@router.head("/mark_recording_consent")
@router.get("/mark_question_asked")
@router.head("/mark_question_asked")
async def interview_tool_probe():
    return {"ok": True, "endpoint": "interview_telnyx_tools"}


@router.post("/end_call")
async def interview_end_call(request: Request, db: Session = Depends(get_db)):
    payload = await _verified_json(request, db)
    try:
        return hangup_interview_call(db, payload)
    except Exception as exc:
        logger.exception("interview_end_call_tool_failed")
        raise HTTPException(status_code=500, detail=str(exc)[:200]) from exc


@router.post("/mark_recording_consent")
async def interview_mark_recording_consent(request: Request, db: Session = Depends(get_db)):
    payload = await _verified_json(request, db)
    try:
        args = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        consented = str(args.get("consented") or args.get("consent") or "yes").strip().lower()
        signal = "recording_consent" if consented not in {"no", "false", "0", "declined"} else "recording_declined"
        return mark_interview_session_signal(db, payload, signal=signal)
    except Exception as exc:
        logger.exception("interview_mark_recording_consent_failed")
        raise HTTPException(status_code=500, detail=str(exc)[:200]) from exc


@router.post("/mark_question_asked")
async def interview_mark_question_asked(request: Request, db: Session = Depends(get_db)):
    payload = await _verified_json(request, db)
    try:
        return mark_interview_session_signal(db, payload, signal="question_asked")
    except Exception as exc:
        logger.exception("interview_mark_question_asked_failed")
        raise HTTPException(status_code=500, detail=str(exc)[:200]) from exc
