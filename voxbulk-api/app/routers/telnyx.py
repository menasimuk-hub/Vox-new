from __future__ import annotations

import json
import base64

from fastapi import APIRouter, Depends, Header, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, get_sessionmaker
from app.models.call_log import CallLog
from app.services.agents.base import AgentRunRequest, AgentRuntimeContext
from app.services.agents.manager import AgentManager
from app.services.telnyx_inbound_messaging_service import TelnyxInboundMessagingService
from app.services.telnyx_voice_service import TelnyxCallerIdService, TelnyxExecutionService
from app.services.voice_agent_service import AzureSpeechService

router = APIRouter(prefix="/telnyx", tags=["telnyx"])


@router.get("/webhooks/voice")
@router.head("/webhooks/voice")
async def telnyx_voice_webhook_probe():
    """Telnyx portal / browser checks often GET the webhook URL — return 200 so it is not 'file not found'."""
    return {"ok": True, "endpoint": "telnyx_voice_webhook"}


@router.post("/webhooks/voice")
async def telnyx_voice_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_retover_org_id: str | None = Header(default=None, alias="X-Retover-Org-Id"),
):
    payload = await request.json()
    log = TelnyxExecutionService.log_call_event(db, payload=payload, org_id=x_retover_org_id)
    return {"ok": True, "log_id": log.id if log else None}


@router.post("/webhooks/voice-events")
async def telnyx_voice_events_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_retover_org_id: str | None = Header(default=None, alias="X-Retover-Org-Id"),
):
    payload = await request.json()
    log = TelnyxExecutionService.log_call_event(db, payload=payload, org_id=x_retover_org_id)
    return {"ok": True, "log_id": log.id if log else None}


@router.get("/webhooks/status")
@router.head("/webhooks/status")
async def telnyx_status_webhook_probe():
    return {"ok": True, "endpoint": "telnyx_status_webhook"}


@router.post("/webhooks/status")
async def telnyx_status_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_retover_org_id: str | None = Header(default=None, alias="X-Retover-Org-Id"),
):
    payload = await request.json()
    log = TelnyxExecutionService.log_call_event(db, payload=payload, org_id=x_retover_org_id)
    return {"ok": True, "log_id": log.id if log else None}


@router.get("/webhooks/verified-numbers")
@router.head("/webhooks/verified-numbers")
async def telnyx_verified_numbers_webhook_probe():
    return {"ok": True, "endpoint": "telnyx_verified_numbers_webhook"}


@router.post("/webhooks/verified-numbers")
async def telnyx_verified_numbers_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    user = TelnyxCallerIdService.mark_webhook(db, payload=payload)
    return {"ok": True, "user_id": user.id if user else None}


@router.get("/webhooks/messages")
@router.head("/webhooks/messages")
async def telnyx_messages_webhook_probe():
    return {"ok": True, "endpoint": "telnyx_messages_webhook"}


@router.post("/webhooks/messages")
async def telnyx_messages_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_retover_org_id: str | None = Header(default=None, alias="X-Retover-Org-Id"),
):
    payload = await request.json()
    result = TelnyxInboundMessagingService.handle_webhook(db, payload, header_org_id=x_retover_org_id)
    return result


@router.get("/webhooks/zoom")
@router.head("/webhooks/zoom")
async def telnyx_zoom_webhook_probe():
    return {"ok": True, "endpoint": "telnyx_zoom_webhook"}


@router.post("/webhooks/zoom")
async def telnyx_zoom_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    from app.services.interview_zoom_service import InterviewZoomService

    return InterviewZoomService.handle_webhook(db, payload)


@router.websocket("/media-stream")
async def telnyx_media_stream(websocket: WebSocket):
    await websocket.accept()
    sessionmaker = get_sessionmaker()
    try:
        while True:
            message = await websocket.receive_text()
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "Invalid JSON media event"})
                continue

            call_control_id = str(
                event.get("call_control_id")
                or event.get("callControlId")
                or ((event.get("stream") or {}).get("call_control_id") if isinstance(event.get("stream"), dict) else "")
                or ""
            )
            transcript = str(event.get("transcript") or event.get("text") or "").strip()
            media_payload = ""
            media = event.get("media")
            if isinstance(media, dict):
                media_payload = str(media.get("payload") or "")
            if not call_control_id:
                await websocket.send_json({"type": "ack", "status": "ignored", "detail": "Missing call_control_id"})
                continue
            if not transcript and media_payload:
                try:
                    audio = base64.b64decode(media_payload)
                    with sessionmaker() as db:
                        transcript = AzureSpeechService.transcribe_audio(db, audio=audio, content_type="audio/basic")
                except Exception:
                    transcript = ""
            if not transcript:
                await websocket.send_json({"type": "ack", "status": "received"})
                continue

            with sessionmaker() as db:
                request = AgentRunRequest(
                    context=AgentRuntimeContext(org_id="", call_control_id=call_control_id),
                    latest_user_utterance=transcript,
                )
                log = db.execute(select(CallLog).where(CallLog.external_call_id == call_control_id)).scalar_one_or_none()
                org_id = log.org_id if log else ""
                request = AgentRunRequest(
                    context=AgentRuntimeContext(
                        org_id=org_id,
                        call_log_id=log.id if log else None,
                        call_control_id=call_control_id,
                        appointment_id=log.appointment_id if log else None,
                        patient_id=log.patient_id if log else None,
                        user_id=log.user_id if log else None,
                        agent_id=log.media_stream_id if log else None,
                    ),
                    latest_user_utterance=transcript,
                )
                result = AgentManager.handle_turn(db, request)
                AgentManager.append_turn_to_call_log(db, call_control_id=call_control_id, caller_text=transcript, result=result)
            await websocket.send_json(
                {
                    "type": "agent_response",
                    "call_control_id": call_control_id,
                    "agent_id": result.agent_id,
                    "text": result.assistant_text,
                    "audio_b64": result.audio_b64,
                }
            )
    except WebSocketDisconnect:
        return
