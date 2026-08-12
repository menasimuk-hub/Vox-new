from __future__ import annotations

import base64
import hmac
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, get_sessionmaker
from app.models.call_log import CallLog
from app.services.agents.base import AgentRunRequest, AgentRuntimeContext
from app.services.agents.manager import AgentManager
from app.services.telnyx_inbound_messaging_service import TelnyxInboundMessagingService
from app.services.telnyx_voice_service import TelnyxCallerIdService, TelnyxExecutionService
from app.services.telnyx_webhook_security import TelnyxWebhookVerificationError, verify_telnyx_webhook
from app.services.voice_agent_service import AzureSpeechService

router = APIRouter(prefix="/telnyx", tags=["telnyx"])
logger = logging.getLogger(__name__)


async def _verified_telnyx_payload(request: Request, db: Session) -> dict:
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
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload") from exc
    return payload if isinstance(payload, dict) else {}


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
    payload = await _verified_telnyx_payload(request, db)
    try:
        from app.services.ai_demo_service import AiDemoService

        AiDemoService.try_bind_call_from_voice_webhook(db, payload=payload)
    except Exception:
        logger.exception("ai_demo_voice_webhook_bind_hook_failed")
    log = TelnyxExecutionService.log_call_event(db, payload=payload, org_id=x_retover_org_id)
    return {"ok": True, "log_id": log.id if log else None}


@router.post("/webhooks/voice-events")
async def telnyx_voice_events_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_retover_org_id: str | None = Header(default=None, alias="X-Retover-Org-Id"),
):
    payload = await _verified_telnyx_payload(request, db)
    try:
        from app.services.ai_demo_service import AiDemoService

        AiDemoService.try_bind_call_from_voice_webhook(db, payload=payload)
    except Exception:
        logger.exception("ai_demo_voice_events_bind_hook_failed")
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
    payload = await _verified_telnyx_payload(request, db)
    log = TelnyxExecutionService.log_call_event(db, payload=payload, org_id=x_retover_org_id)
    return {"ok": True, "log_id": log.id if log else None}


@router.get("/webhooks/verified-numbers")
@router.head("/webhooks/verified-numbers")
async def telnyx_verified_numbers_webhook_probe():
    return {"ok": True, "endpoint": "telnyx_verified_numbers_webhook"}


@router.post("/webhooks/verified-numbers")
async def telnyx_verified_numbers_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await _verified_telnyx_payload(request, db)
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
):
    # TELNYX_WEBHOOK_BUILD_MARKER_20260606_2250 — router inbound instrumentation
    from app.core.runtime_build_info import WEBHOOK_BUILD_MARKER, log_webhook_entry

    payload = await _verified_telnyx_payload(request, db)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    record = data.get("payload") if isinstance(data.get("payload"), dict) else data
    event_type = str(data.get("event_type") or payload.get("event_type") or "").strip()
    from_block = record.get("from") if isinstance(record, dict) else None
    from_phone = ""
    if isinstance(from_block, dict):
        from_phone = str(from_block.get("phone_number") or from_block.get("number") or "").strip()
    elif isinstance(from_block, str):
        from_phone = from_block.strip()

    log_webhook_entry(
        event_type=event_type,
        from_phone=from_phone,
        org_id=None,
        handler="app.routers.telnyx.telnyx_messages_webhook",
    )
    logger.info(
        "%s router_dispatch file=app/routers/telnyx.py endpoint=telnyx_messages_webhook",
        WEBHOOK_BUILD_MARKER,
    )
    # Tenant org is resolved from To-number / connection profile — never from client headers (M8).
    result = TelnyxInboundMessagingService.handle_webhook(db, payload)
    return result


def _media_stream_expected_token(db: Session | None = None) -> str:
    """Shared secret Telnyx must present as ?token= on the media-stream WebSocket URL."""
    if db is None:
        return ""
    try:
        from app.services.provider_settings import ProviderSettingsService

        cfg, _enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
        if isinstance(cfg, dict):
            return str(cfg.get("media_stream_token") or "").strip()
    except Exception:
        logger.debug("media_stream_token_lookup_failed", exc_info=True)
    return ""


@router.websocket("/media-stream")
async def telnyx_media_stream(websocket: WebSocket):
    from app.services.telnyx_webhook_security import webhook_signature_required

    sessionmaker = get_sessionmaker()
    with sessionmaker() as db:
        expected_token = _media_stream_expected_token(db)
    provided = str(
        websocket.query_params.get("token") or websocket.query_params.get("stream_token") or ""
    ).strip()

    # Fail closed outside test/insecure mode: require a configured stream token and a match.
    if webhook_signature_required():
        if not expected_token or not provided or not hmac.compare_digest(provided, expected_token):
            await websocket.close(code=1008)
            return
    elif expected_token and provided and not hmac.compare_digest(provided, expected_token):
        await websocket.close(code=1008)
        return

    await websocket.accept()
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

            with sessionmaker() as db:
                log = db.execute(select(CallLog).where(CallLog.external_call_id == call_control_id)).scalar_one_or_none()
                if log is None:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "status": "rejected",
                            "detail": "Unknown call_control_id",
                        }
                    )
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
                log = db.execute(select(CallLog).where(CallLog.external_call_id == call_control_id)).scalar_one_or_none()
                if log is None:
                    await websocket.send_json(
                        {"type": "error", "status": "rejected", "detail": "Unknown call_control_id"}
                    )
                    continue
                org_id = log.org_id or ""
                request = AgentRunRequest(
                    context=AgentRuntimeContext(
                        org_id=org_id,
                        call_log_id=log.id,
                        call_control_id=call_control_id,
                        appointment_id=log.appointment_id,
                        patient_id=log.patient_id,
                        user_id=log.user_id,
                        agent_id=log.media_stream_id,
                    ),
                    latest_user_utterance=transcript,
                )
                result = AgentManager.handle_turn(db, request)
                AgentManager.append_turn_to_call_log(
                    db, call_control_id=call_control_id, caller_text=transcript, result=result
                )
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
