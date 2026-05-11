from __future__ import annotations

import base64
import json
import logging
import os
import time
from uuid import uuid4

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db
from app.models.agent import AgentDefinition
from app.models.call_log import CallLog
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.agents.base import AgentMessage, AgentRunRequest, AgentRuntimeContext
from app.services.agents.manager import AgentManager
from app.services.agents.tools import AgentToolRegistry
from app.services.providers.azure_speech import AzureSpeechProviderService
from app.services.providers.elevenlabs_service import ElevenLabsProviderService
from app.services.providers.openai_service import OpenAIProviderService
from app.services.provider_settings import ProviderSettingsService
from app.services.telnyx_voice_service import TelnyxExecutionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/demo", tags=["demo"])
admin_router = APIRouter(prefix="/admin/demo", tags=["admin-demo"])
FAST_DEMO_MODEL = "gpt-4o-mini"
FAST_DEMO_MAX_TOKENS = 80
FAST_DEMO_TEMPERATURE = 0.45
FAST_DEMO_TTS_FORMAT = "browser_fast"
FAST_DEMO_AUDIO_MIME = "audio/mpeg"
DEMO_VOICE_OPTIONS = {
    AzureSpeechProviderService.BROWSER_VOICE_ID,
    AzureSpeechProviderService.BROWSER_BACKUP_VOICE_ID,
}
DEMO_RATE_OPTIONS = {"normal", "slightly_fast"}
DEMO_PROVIDERS = {"openai", "deepseek", "vapi", "telnyx"}
DEMO_TTS_PROVIDERS = {"azure_speech", "elevenlabs"}
DEMO_STT_PROVIDERS = {"browser", "azure_speech", "elevenlabs"}


def _slugify(raw: str) -> str:
    s = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(raw or "").strip())
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def _first_org_id_for_user(db: Session, user_id: str) -> str:
    org_id = db.execute(
        select(OrganisationMembership.org_id).where(OrganisationMembership.user_id == user_id).order_by(OrganisationMembership.created_at.asc()).limit(1)
    ).scalar_one_or_none()
    if org_id:
        return org_id
    fallback = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
    if fallback:
        return fallback
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No organisation exists for demo agent context")


def _resolve_demo_agent(db: Session, raw_slug: str) -> AgentDefinition:
    wanted = _slugify(raw_slug or "vox-sales")
    agent = db.execute(
        select(AgentDefinition).where(func.lower(AgentDefinition.slug) == wanted, AgentDefinition.is_active.is_(True))
    ).scalar_one_or_none()
    if agent is not None:
        return agent

    raw_name = str(raw_slug or "").strip().lower()
    agent = db.execute(
        select(AgentDefinition).where(func.lower(AgentDefinition.name) == raw_name, AgentDefinition.is_active.is_(True))
    ).scalar_one_or_none()
    if agent is not None:
        return agent

    active_agents = list(db.execute(select(AgentDefinition).where(AgentDefinition.is_active.is_(True))).scalars())
    for candidate in active_agents:
        if _slugify(candidate.name) == wanted or _slugify(candidate.slug) == wanted:
            return candidate
    if wanted in {"vox-sales", "vox-sale"}:
        for candidate in active_agents:
            haystack = f"{candidate.name} {candidate.slug}".lower()
            if "vox" in haystack and ("sales" in haystack or "sale" in haystack):
                return candidate

    available = [{"name": a.name, "slug": a.slug} for a in active_agents]
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"message": f"Active agent not found for slug/name '{raw_slug or 'vox-sales'}'", "available_agents": available},
    )


def _history_from_payload(payload: dict) -> list[AgentMessage]:
    rows = payload.get("history") or []
    if not isinstance(rows, list):
        return []
    messages: list[AgentMessage] = []
    for row in rows[-12:]:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip()
        content = str(row.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append(AgentMessage(role=role, content=content))
    return messages


def _ms(start: float, end: float | None = None) -> int:
    return int(((end or time.perf_counter()) - start) * 1000)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_for(request_id: str, event: str, data: dict) -> str:
    return _sse(event, {"request_id": request_id, **data})


def _demo_voice_id(payload: dict) -> str:
    requested = str(payload.get("voice_id") or "").strip()
    return requested if requested in DEMO_VOICE_OPTIONS else AzureSpeechProviderService.BROWSER_VOICE_ID


def _demo_speaking_rate(payload: dict) -> str:
    requested = str(payload.get("speaking_rate") or "normal").strip().lower()
    return requested if requested in DEMO_RATE_OPTIONS else "normal"


def _demo_provider(payload: dict) -> str:
    requested = str(payload.get("provider") or "openai").strip().lower()
    return requested if requested in DEMO_PROVIDERS else "openai"


def _demo_model_for_provider(provider: str) -> str | None:
    return None if provider in {"deepseek", "telnyx"} else FAST_DEMO_MODEL


def _demo_tts_provider(payload: dict) -> str:
    requested = str(payload.get("tts_provider") or payload.get("text_to_speech_provider") or "azure_speech").strip().lower()
    return requested if requested in DEMO_TTS_PROVIDERS else "azure_speech"


def _demo_stt_provider(raw: str | None) -> str:
    requested = str(raw or "browser").strip().lower()
    return requested if requested in DEMO_STT_PROVIDERS else "browser"


def _elevenlabs_voice_settings(payload: dict) -> dict:
    raw = payload.get("elevenlabs_voice_settings") if isinstance(payload.get("elevenlabs_voice_settings"), dict) else {}
    allowed = {"stability", "similarity_boost", "style", "speed", "speaker_boost", "model_id", "output_format"}
    return {k: v for k, v in raw.items() if k in allowed}


def _synthesize_demo_audio(db: Session, *, text: str, payload: dict, voice_id: str, speaking_rate: str) -> dict:
    tts_provider = _demo_tts_provider(payload)
    if tts_provider == "elevenlabs":
        return ElevenLabsProviderService.synthesize_text_result(
            db,
            text=text,
            voice_id=str(payload.get("elevenlabs_voice_id") or "").strip() or None,
            voice_settings=_elevenlabs_voice_settings(payload),
        )
    result = AzureSpeechProviderService.synthesize_demo_chunk_result(
        db,
        text=text,
        voice_id=voice_id,
        output_format=FAST_DEMO_TTS_FORMAT,
        speaking_rate=speaking_rate,
    )
    return {**result, "audio_mime": FAST_DEMO_AUDIO_MIME, "voice_id": voice_id}


def _vapi_config(db: Session | None = None) -> dict:
    cfg: dict = {}
    enabled = False
    if db is not None:
        try:
            stored, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="vapi")
            cfg = stored or {}
        except Exception:
            cfg = {}
    env_public_key = str(os.getenv("VAPI_PUBLIC_KEY") or "").strip()
    env_assistant_id = str(os.getenv("VAPI_ASSISTANT_ID") or "").strip()
    public_key = str(cfg.get("public_key") or env_public_key or "").strip()
    assistant_id = str(cfg.get("assistant_id") or env_assistant_id or "").strip()
    api_key = str(cfg.get("api_key") or os.getenv("VAPI_API_KEY") or "").strip()
    return {
        "provider": "vapi",
        "configured": bool((enabled or (env_public_key and env_assistant_id)) and public_key and assistant_id),
        "public_key": public_key,
        "assistant_id": assistant_id,
        "api_key_set": bool(api_key),
        "api_key_length": len(api_key),
        "missing": [name for name, value in {"VAPI_PUBLIC_KEY": public_key, "VAPI_ASSISTANT_ID": assistant_id}.items() if not value],
        "note": "Vapi browser calls use the Vapi Web SDK directly, so Azure chunked playback is not used in this mode.",
    }


@admin_router.get("/provider-config")
def demo_provider_config(db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    deepseek_summary = ProviderSettingsService.get_platform_config_admin_view(db, provider="deepseek")
    elevenlabs_summary = ProviderSettingsService.get_platform_config_admin_view(db, provider="elevenlabs")
    telnyx_summary = ProviderSettingsService.get_platform_config_admin_view(db, provider="telnyx")
    return {
        "providers": {
            "openai": {"configured": True, "voice_mode": "azure_speech_chunks"},
            "deepseek": {
                "configured": bool(deepseek_summary.get("configured") or str(os.getenv("DEEPSEEK_API_KEY") or "").strip()),
                "base_url": str((deepseek_summary.get("config") or {}).get("base_url") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").strip(),
                "model": str((deepseek_summary.get("config") or {}).get("model") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip(),
                "voice_mode": "azure_speech_chunks",
            },
            "vapi": _vapi_config(db),
            "telnyx": {
                "configured": bool(telnyx_summary.get("configured")),
                "voice_mode": "telnyx_outbound_call",
                "missing": telnyx_summary.get("missing_fields") or [],
                "config": telnyx_summary.get("config") or {},
                "secret_set": telnyx_summary.get("secret_set") or {},
            },
            "elevenlabs": {
                "configured": bool(elevenlabs_summary.get("configured")),
                "voice_mode": "elevenlabs_tts",
                "default_voice_id": (elevenlabs_summary.get("config") or {}).get("default_voice_id") or "",
                "config": elevenlabs_summary.get("config") or {},
            },
        }
    }


@admin_router.post("/module-test/tts")
def demo_tts_module_test(payload: dict, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    text = str(payload.get("text") or "Hello, this is your text to speech test.").strip()
    voice_id = _demo_voice_id(payload)
    speaking_rate = _demo_speaking_rate(payload)
    result = _synthesize_demo_audio(db, text=text, payload=payload, voice_id=voice_id, speaking_rate=speaking_rate)
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={k: v for k, v in result.items() if k != "audio_data"})
    audio_data = bytes(result.get("audio_data") or b"")
    return {
        "ok": True,
        "tts_provider": _demo_tts_provider(payload),
        "text": text,
        "voice_id": result.get("voice_id") or voice_id,
        "audio_b64": base64.b64encode(audio_data).decode("ascii"),
        "audio_mime": result.get("audio_mime") or "audio/mpeg",
        "audio_bytes": len(audio_data),
        "timings": result.get("timings") or {},
        "voice_settings": result.get("voice_settings"),
    }


@admin_router.post("/module-test/stt")
async def demo_stt_module_test(
    provider: str = Form("elevenlabs"),
    model_id: str = Form("scribe_v1"),
    language_code: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    selected_provider = _demo_stt_provider(provider)
    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio file is empty")
    if selected_provider != "elevenlabs":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{selected_provider} STT module test is not implemented yet")
    try:
        result = ElevenLabsProviderService.transcribe_audio_result(
            db,
            audio_data=audio_data,
            filename=file.filename or "speech.webm",
            content_type=file.content_type or "audio/webm",
            model_id=model_id or "scribe_v1",
            language_code=(language_code or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"ElevenLabs STT failed: {e}") from e
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
    return {"provider": selected_provider, **result}


@admin_router.post("/module-test/llm")
def demo_llm_module_test(payload: dict, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    provider = _demo_provider(payload)
    if provider == "vapi":
        cfg = _vapi_config(db)
        return {"ok": bool(cfg.get("configured")), "provider": "vapi", "message": "Vapi uses its own assistant runtime for browser calls.", "vapi": cfg}
    if provider == "telnyx":
        cfg = ProviderSettingsService.get_platform_config_admin_view(db, provider="telnyx")
        return {
            "ok": bool(cfg.get("configured")),
            "provider": "telnyx",
            "message": "Telnyx uses the selected Vox Sales agent for real outbound calls. Use Call my phone to test it.",
            "missing": cfg.get("missing_fields") or [],
        }
    prompt = str(payload.get("text") or "What does Vox Sales do?").strip()
    try:
        result = OpenAIProviderService.test_completion_raw(db, prompt=prompt, provider=provider if provider != "openai" else None)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{provider} test failed: {e}") from e
    return {"provider": provider, **result}


def _call_log_out(log: CallLog) -> dict:
    return {
        "id": log.id,
        "provider": log.provider,
        "external_call_id": log.external_call_id,
        "status": log.status,
        "direction": log.direction,
        "to_number": log.to_number,
        "from_number": log.from_number,
        "agent_id": log.media_stream_id,
        "started_at": log.started_at,
        "answered_at": log.answered_at,
        "ended_at": log.ended_at,
        "last_status_at": log.last_status_at,
        "raw_payload": log.raw_payload,
    }


@admin_router.post("/telnyx-call")
def demo_telnyx_call(payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    to_number = str(payload.get("to_number") or "").strip()
    if not to_number:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="to_number is required")
    cfg = ProviderSettingsService.get_platform_config_admin_view(db, provider="telnyx")
    if not cfg.get("configured"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Telnyx settings are incomplete", "missing_fields": cfg.get("missing_fields") or []},
        )
    agent_slug = str(payload.get("agent_slug") or "vox-sales").strip() or "vox-sales"
    agent = _resolve_demo_agent(db, agent_slug)
    org_id = str(payload.get("org_id") or "").strip() or _first_org_id_for_user(db, admin.id)
    try:
        log = TelnyxExecutionService.start_call(
            db,
            org_id=org_id,
            to_number=to_number,
            user_id=admin.id,
            llm_prompt=agent.system_prompt,
            agent_id=agent.id,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Telnyx call failed: {e}") from e
    return {"ok": log.status != "failed", "message": "Telnyx outbound call started.", "call": _call_log_out(log)}


@admin_router.get("/telnyx-call/{call_id}")
def demo_telnyx_call_status(call_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    log = db.execute(select(CallLog).where(CallLog.id == call_id, CallLog.provider == "telnyx")).scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telnyx demo call not found")
    return {"ok": True, "call": _call_log_out(log)}


@router.post("/agent-call")
@admin_router.post("/agent-call")
def demo_agent_call(payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    total_start = time.perf_counter()
    backend_received_ms = _ms(total_start, total_start)
    speech_finalized_ms = payload.get("speech_finalized_ms")
    browser_timings = payload.get("browser_timings") if isinstance(payload.get("browser_timings"), dict) else {}
    agent_slug = str(payload.get("agent_slug") or "vox-sales").strip() or "vox-sales"
    provider = _demo_provider(payload)
    tts_provider = _demo_tts_provider(payload)
    voice_id = _demo_voice_id(payload)
    speaking_rate = _demo_speaking_rate(payload)
    user_text = str(payload.get("input") or "").strip()
    if not user_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input is required")

    if provider == "vapi":
        cfg = _vapi_config(db)
        if not cfg["configured"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": "Vapi is not configured for browser comparison", **cfg})
        return {"ok": True, "provider": "vapi", "agent_slug": agent_slug, "vapi": cfg}

    logger.info(
        "demo_agent_call_received",
        extra={
            "agent_slug": agent_slug,
            "provider": provider,
            "input_chars": len(user_text),
            "speech_finalization_ms": speech_finalized_ms,
            "browser_request_sent_ms": browser_timings.get("request_sent_ms"),
        },
    )
    resolve_start = time.perf_counter()
    resolve_start_ms = _ms(total_start, resolve_start)
    logger.info("demo_agent_resolution_start", extra={"agent_slug": agent_slug, "stage_start_ms": resolve_start_ms})
    agent = _resolve_demo_agent(db, agent_slug)
    resolve_end = time.perf_counter()
    resolve_ms = _ms(resolve_start, resolve_end)
    resolve_end_ms = _ms(total_start, resolve_end)
    org_id = str(payload.get("org_id") or "").strip() or _first_org_id_for_user(db, admin.id)
    logger.info("demo_agent_resolution_end", extra={"agent_slug": agent.slug, "agent_id": agent.id, "org_id": org_id, "stage_end_ms": resolve_end_ms, "agent_resolution_ms": resolve_ms})

    try:
        openai_start = time.perf_counter()
        openai_start_ms = _ms(total_start, openai_start)
        selected_model = _demo_model_for_provider(provider)
        logger.info("demo_llm_start", extra={"agent_slug": agent.slug, "provider": provider, "stage_start_ms": openai_start_ms, "model": selected_model or "provider-default", "max_tokens": FAST_DEMO_MAX_TOKENS})
        result = AgentManager.handle_turn(
            db,
            AgentRunRequest(
                context=AgentRuntimeContext(
                    org_id=org_id,
                    user_id=admin.id,
                    agent_id=agent.id,
                    workflow_type="browser-demo",
                ),
                latest_user_utterance=user_text,
                history=_history_from_payload(payload),
                agent_id=agent.id,
            ),
            synthesize_audio=False,
            llm_model=selected_model,
            llm_max_tokens=FAST_DEMO_MAX_TOKENS,
            llm_temperature=FAST_DEMO_TEMPERATURE,
            llm_provider=provider if provider != "openai" else None,
        )
        openai_end = time.perf_counter()
        openai_ms = _ms(openai_start, openai_end)
        openai_end_ms = _ms(total_start, openai_end)
        logger.info("demo_llm_end", extra={"agent_slug": agent.slug, "provider": provider, "stage_end_ms": openai_end_ms, "openai_ms": openai_ms, "reply_chars": len(result.assistant_text or "")})
    except Exception as e:
        logger.exception("demo_agent_call_openai_failed", extra={"agent_slug": agent.slug})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Agent/{provider} failed: {e}") from e

    try:
        tts_start = time.perf_counter()
        tts_start_ms = _ms(total_start, tts_start)
        logger.info("demo_tts_start", extra={"agent_slug": agent.slug, "stage_start_ms": tts_start_ms, "tts_provider": tts_provider, "tts_format": FAST_DEMO_TTS_FORMAT, "text_chars": len(result.assistant_text or "")})
        tts = _synthesize_demo_audio(
            db,
            text=result.assistant_text,
            payload=payload,
            voice_id=voice_id,
            speaking_rate=speaking_rate,
        )
        tts_end = time.perf_counter()
        tts_ms = _ms(tts_start, tts_end)
        tts_end_ms = _ms(total_start, tts_end)
        logger.info("demo_tts_end", extra={"agent_slug": agent.slug, "stage_end_ms": tts_end_ms, "tts_provider": tts_provider, "tts_ms": tts_ms, "audio_bytes": int(tts.get("audio_bytes") or 0)})
    except Exception as e:
        logger.exception("demo_agent_call_tts_failed", extra={"agent_slug": agent.slug, "tts_provider": tts_provider})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{tts_provider} TTS failed: {e}") from e
    if not tts.get("ok"):
        logger.error("demo_agent_call_tts_cancelled", extra={"agent_slug": agent.slug, "tts_provider": tts_provider, "error_code": tts.get("error_code"), "error_details": tts.get("error_details")})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"message": f"{tts_provider} TTS failed", **tts})

    audio_data = bytes(tts.get("audio_data") or b"")
    audio_b64 = base64.b64encode(audio_data).decode("ascii")
    response_returned_ms = _ms(total_start)
    timings = {
        "backend_request_received_ms": backend_received_ms,
        "speech_finalization_ms": speech_finalized_ms,
        "browser_request_sent_ms": browser_timings.get("request_sent_ms"),
        "agent_resolution_start_ms": resolve_start_ms,
        "agent_resolution_end_ms": resolve_end_ms,
        "agent_resolution_ms": resolve_ms,
        "openai_start_ms": openai_start_ms,
        "openai_end_ms": openai_end_ms,
        "openai_ms": openai_ms,
        "azure_tts_start_ms": tts_start_ms,
        "azure_tts_end_ms": tts_end_ms,
        "azure_tts_ms": tts_ms,
        "response_returned_ms": response_returned_ms,
        "total_roundtrip_ms": response_returned_ms,
        "selected_provider": provider,
        "tts_provider": tts_provider,
        **((result.transcript_metadata or {}).get("timings") or {}),
        **(tts.get("timings") or {}),
    }
    logger.info(
        "demo_agent_call_timings",
        extra={
            "agent_slug": result.agent_slug,
            "speech_finalization_ms": speech_finalized_ms,
            "browser_request_sent_ms": timings["browser_request_sent_ms"],
            "backend_request_received_ms": timings["backend_request_received_ms"],
            "agent_resolution_ms": resolve_ms,
            "openai_ms": openai_ms,
            "azure_tts_ms": tts_ms,
            "response_returned_ms": timings["response_returned_ms"],
            "total_roundtrip_ms": timings["total_roundtrip_ms"],
            "model": selected_model or "provider-default",
            "max_tokens": FAST_DEMO_MAX_TOKENS,
            "tts_format": FAST_DEMO_TTS_FORMAT,
        },
    )

    return {
        "ok": True,
        "provider": provider,
        "agent_slug": result.agent_slug,
        "user_text": user_text,
        "agent_text": result.assistant_text,
        "audio_b64": audio_b64,
        "audio_bytes": int(tts.get("audio_bytes") or len(audio_data)),
        "audio_mime": tts.get("audio_mime") or FAST_DEMO_AUDIO_MIME,
        "usage": result.usage,
        "timings": timings,
        "voice": {
            "voice_id": voice_id,
            "tts_provider": tts_provider,
            "output_format": "audio/mpeg",
            "ssml": f"prosody rate {AzureSpeechProviderService._prosody_rate(speaking_rate)}, pitch default, medium volume, short natural pause",
        },
    }


@router.post("/agent-call/stream")
@admin_router.post("/agent-call/stream")
def demo_agent_call_stream(payload: dict, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    total_start = time.perf_counter()
    request_id = str(payload.get("request_id") or uuid4())
    agent_slug = str(payload.get("agent_slug") or "vox-sales").strip() or "vox-sales"
    provider = _demo_provider(payload)
    tts_provider = _demo_tts_provider(payload)
    voice_id = _demo_voice_id(payload)
    speaking_rate = _demo_speaking_rate(payload)
    browser_timings = payload.get("browser_timings") if isinstance(payload.get("browser_timings"), dict) else {}
    user_text = str(payload.get("input") or "").strip()
    if not user_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input is required")

    def stream_events():
        first_text_ms: int | None = None
        first_sentence_ms: int | None = None
        first_audio_ms: int | None = None
        chunk_index = 0
        audio_index = 0
        assistant_text = ""
        chunk_buffer = ""
        chunk_buffer_started: float | None = None
        agent = None

        def disconnected() -> bool:
            try:
                return bool(anyio.from_thread.run(request.is_disconnected))
            except Exception:
                return False

        try:
            if provider == "vapi":
                cfg = _vapi_config(db)
                if not cfg["configured"]:
                    yield _sse_for(request_id, "error", {"message": "Vapi is not configured for browser comparison", "provider": "vapi", "detail": cfg})
                    return
                yield _sse_for(request_id, "vapi_config", cfg)
                yield _sse_for(request_id, "done", {"agent_slug": agent_slug, "agent_text": "", "provider": "vapi", "metrics": {"completed_ms": _ms(total_start), "full_complete": _ms(total_start)}})
                return

            yield _sse_for(
                request_id,
                "transcript_received",
                {
                    "user_text": user_text,
                    "agent_slug": agent_slug,
                    "provider": provider,
                    "browser_speech_finalized": payload.get("speech_finalized_ms"),
                    "request_sent": browser_timings.get("request_sent_ms"),
                    "elapsed_ms": _ms(total_start),
                },
            )

            resolve_start = time.perf_counter()
            agent = _resolve_demo_agent(db, agent_slug)
            org_id = str(payload.get("org_id") or "").strip() or _first_org_id_for_user(db, admin.id)
            resolve_ms = _ms(resolve_start)
            yield _sse_for(
                request_id,
                "metrics",
                {
                    "agent_resolution_ms": resolve_ms,
                    "backend_request_received_ms": 0,
                    "selected_provider": provider,
                    "browser_speech_finalized": payload.get("speech_finalized_ms"),
                    "request_sent": browser_timings.get("request_sent_ms"),
                },
            )

            context = AgentRuntimeContext(
                org_id=org_id,
                user_id=admin.id,
                agent_id=agent.id,
                workflow_type="browser-demo",
            )
            history = _history_from_payload(payload)
            messages = history + [AgentMessage(role="user", content=user_text)]
            tools = AgentToolRegistry.definitions(
                allow_lookup=agent.allow_lookup_tool,
                allow_booking=agent.allow_booking_tool,
                allow_reschedule=agent.allow_reschedule_tool,
                allow_cancel=agent.allow_cancel_tool,
            )
            system_prompt = AgentManager.build_system_prompt(db, agent=agent, context=context)

            llm_start = time.perf_counter()
            selected_model = _demo_model_for_provider(provider)
            stream_kwargs = {
                "model": selected_model,
                "tools": tools,
                "max_tokens": FAST_DEMO_MAX_TOKENS,
                "temperature": FAST_DEMO_TEMPERATURE,
            }
            if provider != "openai":
                stream_kwargs["provider"] = provider
            for delta in OpenAIProviderService.stream_complete(
                db,
                system_prompt=system_prompt,
                messages=messages,
                **stream_kwargs,
            ):
                if disconnected():
                    logger.info("demo_agent_call_stream_disconnected", extra={"agent_slug": agent_slug, "request_id": request_id})
                    return
                if first_text_ms is None:
                    first_text_ms = _ms(total_start)
                    yield _sse_for(request_id, "metrics", {"first_openai_token": first_text_ms, "first_llm_token_ms": first_text_ms, "selected_provider": provider})
                assistant_text += delta
                if not chunk_buffer.strip():
                    chunk_buffer_started = time.perf_counter()
                chunk_buffer = f"{chunk_buffer}{delta}"
                yield _sse_for(request_id, "llm_text_delta", {"delta": delta, "elapsed_ms": _ms(total_start)})

                while True:
                    force_flush = chunk_buffer_started is not None and (time.perf_counter() - chunk_buffer_started) >= 1.5
                    speakable, chunk_buffer = AzureSpeechProviderService.pop_speakable_chunk(
                        chunk_buffer,
                        force=force_flush,
                        min_words=8 if chunk_index == 0 else 12,
                    )
                    if not speakable:
                        break
                    if disconnected():
                        logger.info("demo_agent_call_stream_disconnected", extra={"agent_slug": agent_slug, "request_id": request_id})
                        return
                    chunk_buffer_started = time.perf_counter() if chunk_buffer.strip() else None
                    chunk_index += 1
                    if first_sentence_ms is None:
                        first_sentence_ms = _ms(total_start)
                        yield _sse_for(request_id, "metrics", {"first_sentence_ready": first_sentence_ms, "first_sentence_ready_ms": first_sentence_ms})
                    yield _sse_for(request_id, "llm_sentence_ready", {"index": chunk_index, "text": speakable, "elapsed_ms": _ms(total_start)})
                    tts_start = time.perf_counter()
                    tts = _synthesize_demo_audio(
                        db,
                        text=speakable,
                        payload=payload,
                        voice_id=voice_id,
                        speaking_rate=speaking_rate,
                    )
                    if not tts.get("ok"):
                        yield _sse_for(request_id, "error", {"message": f"{tts_provider} TTS failed", "detail": {k: v for k, v in tts.items() if k != "audio_data"}})
                        return
                    audio_index += 1
                    if first_audio_ms is None:
                        first_audio_ms = _ms(total_start)
                    audio_data = bytes(tts.get("audio_data") or b"")
                    tts_timings = tts.get("timings") or {}
                    yield _sse_for(
                        request_id,
                        "tts_audio_ready",
                        {
                            "index": audio_index,
                            "text": speakable,
                            "tts_provider": tts_provider,
                            "voice_id": tts.get("voice_id") or voice_id,
                            "speaking_rate": speaking_rate,
                            "audio_b64": base64.b64encode(audio_data).decode("ascii"),
                            "audio_mime": tts.get("audio_mime") or FAST_DEMO_AUDIO_MIME,
                            "audio_bytes": len(audio_data),
                            "tts_ms": _ms(tts_start),
                            "azure_first_byte": tts_timings.get("azure_first_byte_ms"),
                            "azure_chunk_finish": tts_timings.get("azure_chunk_finish_ms"),
                            "elapsed_ms": _ms(total_start),
                            "is_first_audio": audio_index == 1,
                        },
                    )

            llm_ms = _ms(llm_start)
            while True:
                speakable, chunk_buffer = AzureSpeechProviderService.pop_speakable_chunk(chunk_buffer, final=True)
                if not speakable:
                    break
                if disconnected():
                    logger.info("demo_agent_call_stream_disconnected", extra={"agent_slug": agent_slug, "request_id": request_id})
                    return
                chunk_index += 1
                if first_sentence_ms is None:
                    first_sentence_ms = _ms(total_start)
                    yield _sse_for(request_id, "metrics", {"first_sentence_ready": first_sentence_ms, "first_sentence_ready_ms": first_sentence_ms})
                yield _sse_for(request_id, "llm_sentence_ready", {"index": chunk_index, "text": speakable, "elapsed_ms": _ms(total_start)})
                tts_start = time.perf_counter()
                tts = _synthesize_demo_audio(
                    db,
                    text=speakable,
                    payload=payload,
                    voice_id=voice_id,
                    speaking_rate=speaking_rate,
                )
                if not tts.get("ok"):
                    yield _sse_for(request_id, "error", {"message": f"{tts_provider} TTS failed", "detail": {k: v for k, v in tts.items() if k != "audio_data"}})
                    return
                audio_index += 1
                if first_audio_ms is None:
                    first_audio_ms = _ms(total_start)
                audio_data = bytes(tts.get("audio_data") or b"")
                tts_timings = tts.get("timings") or {}
                yield _sse_for(
                    request_id,
                    "tts_audio_ready",
                    {
                        "index": audio_index,
                        "text": speakable,
                        "tts_provider": tts_provider,
                        "voice_id": tts.get("voice_id") or voice_id,
                        "speaking_rate": speaking_rate,
                        "audio_b64": base64.b64encode(audio_data).decode("ascii"),
                        "audio_mime": tts.get("audio_mime") or FAST_DEMO_AUDIO_MIME,
                        "audio_bytes": len(audio_data),
                        "tts_ms": _ms(tts_start),
                        "azure_first_byte": tts_timings.get("azure_first_byte_ms"),
                        "azure_chunk_finish": tts_timings.get("azure_chunk_finish_ms"),
                        "elapsed_ms": _ms(total_start),
                        "is_first_audio": audio_index == 1,
                    },
                )

            yield _sse_for(
                request_id,
                "done",
                {
                    "agent_slug": agent.slug,
                    "agent_text": assistant_text.strip(),
                    "provider": provider,
                    "metrics": {
                        "selected_provider": provider,
                        "tts_provider": tts_provider,
                        "first_text_ms": first_text_ms,
                        "first_openai_token": first_text_ms,
                        "first_sentence_ready_ms": first_sentence_ms,
                        "first_sentence_ready": first_sentence_ms,
                        "first_audio_ms": first_audio_ms,
                        "llm_stream_ms": llm_ms,
                        "completed_ms": _ms(total_start),
                        "full_complete": _ms(total_start),
                        "audio_chunks": audio_index,
                    },
                },
            )
        except GeneratorExit:
            logger.info("demo_agent_call_stream_disconnected", extra={"agent_slug": agent_slug, "request_id": request_id})
            raise
        except Exception as e:
            logger.exception("demo_agent_call_stream_failed", extra={"agent_slug": agent_slug})
            yield _sse_for(request_id, "error", {"message": str(e), "elapsed_ms": _ms(total_start)})
    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
