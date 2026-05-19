from __future__ import annotations

import base64
import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any
from uuid import uuid4

import anyio
import websockets
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db, get_sessionmaker
from app.core.security import decode_token
from app.models.agent import AgentDefinition
from app.models.admin_user import AdminUser
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.agents.base import AgentMessage, AgentRunRequest, AgentRuntimeContext
from app.services.agents.manager import AgentManager
from app.services.agents.tools import AgentToolRegistry
from app.services.providers.azure_speech import AzureSpeechProviderService
from app.services.providers.cartesia_service import CartesiaProviderService
from app.services.providers.deepgram_service import DeepgramProviderService, deepgram_transcript_from_ws_message
from app.services.providers.elevenlabs_service import ElevenLabsProviderService
from app.services.providers.groq_service import GroqProviderService
from app.services.providers.openai_service import OpenAIProviderService
from app.services.provider_settings import ProviderSettingsService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/demo", tags=["demo"])
admin_router = APIRouter(prefix="/admin/demo", tags=["admin-demo"])
FAST_DEMO_MODEL = "gpt-4o-mini"
FAST_DEMO_MAX_TOKENS = 80
FAST_DEMO_TEMPERATURE = 0.45
REALTIME_GROQ_MODEL = "llama-3.3-70b-versatile"
REALTIME_SYSTEM_PROMPT = "Dental assistant. Brief, friendly. Answer in 1-2 short sentences."
REALTIME_GROQ_MODEL_OPTIONS = {"llama-3.3-70b-versatile", "llama-3.1-8b-instant"}
REALTIME_MAX_TOKENS = 100
REALTIME_TEMPERATURE = 0.7
REALTIME_ENDPOINT_TIMEOUT_SECONDS = 1.0
FAST_DEMO_TTS_FORMAT = "browser_fast"
FAST_DEMO_AUDIO_MIME = "audio/mpeg"
DEMO_VOICE_OPTIONS = {
    AzureSpeechProviderService.BROWSER_VOICE_ID,
    AzureSpeechProviderService.BROWSER_BACKUP_VOICE_ID,
}
DEMO_RATE_OPTIONS = {"normal", "slightly_fast"}
DEMO_PROVIDERS = {"openai", "deepseek", "groq", "vapi"}
DEMO_STT_PROVIDERS = {"browser", "azure_speech", "elevenlabs", "groq", "deepgram"}
DEMO_TTS_PROVIDERS = {"azure_speech", "elevenlabs", "groq_orpheus", "cartesia"}
GROQ_ORPHEUS_VOICES = {"austin", "diana"}


def _require_ws_admin(token: str, db: Session) -> User:
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise PermissionError("Invalid token") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise PermissionError("Invalid token")
    user = db.execute(select(User).where(User.id == str(user_id))).scalar_one_or_none()
    if user is None:
        raise PermissionError("Invalid token")
    if user.is_superuser:
        return user
    admin_user = db.execute(select(AdminUser).where(AdminUser.id == user.id)).scalar_one_or_none()
    if admin_user is None and user.email:
        admin_user = db.execute(select(AdminUser).where(AdminUser.email == user.email.strip().lower())).scalar_one_or_none()
    if admin_user is not None and admin_user.is_active:
        return user
    raise PermissionError("Platform admin access required")


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
    if active_agents:
        return active_agents[0]

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
    if str(payload.get("tts_provider") or "").strip().lower() in {"cartesia", "elevenlabs"}:
        return requested
    return requested if requested in DEMO_VOICE_OPTIONS else AzureSpeechProviderService.BROWSER_VOICE_ID


def _demo_tts_voice_id(payload: dict, fallback: str = "") -> str:
    tts_provider = _demo_tts_provider(payload)
    if tts_provider == "cartesia":
        return str(payload.get("cartesia_voice_id") or payload.get("voice_id") or fallback or "").strip()
    if tts_provider == "elevenlabs":
        return str(payload.get("elevenlabs_voice_id") or payload.get("voice_id") or fallback or "").strip()
    return fallback


def _demo_speaking_rate(payload: dict) -> str:
    requested = str(payload.get("speaking_rate") or "normal").strip().lower()
    return requested if requested in DEMO_RATE_OPTIONS else "normal"


def _demo_provider(payload: dict) -> str:
    requested = str(payload.get("provider") or "openai").strip().lower()
    return requested if requested in DEMO_PROVIDERS else "openai"


def _demo_model_for_provider(provider: str) -> str | None:
    return None if provider in {"deepseek", "groq"} else FAST_DEMO_MODEL

def _demo_stt_provider(raw: str | None) -> str:
    requested = str(raw or "browser").strip().lower()
    return requested if requested in DEMO_STT_PROVIDERS else "browser"


def _demo_tts_provider(payload: dict) -> str:
    requested = str(payload.get("tts_provider") or "azure_speech").strip().lower()
    return requested if requested in DEMO_TTS_PROVIDERS else "azure_speech"


def _groq_tts_voice(payload: dict) -> str:
    requested = str(payload.get("groq_tts_voice") or "austin").strip().lower()
    return requested if requested in GROQ_ORPHEUS_VOICES else "austin"


def _synthesize_demo_audio(db: Session, *, text: str, payload: dict, voice_id: str, speaking_rate: str, streaming_chunk: bool = False) -> dict:
    if not str(text or "").strip():
        return {"ok": False, "error": "empty_tts_text", "message": "Skipped empty TTS request"}
    tts_provider = _demo_tts_provider(payload)
    if tts_provider == "groq_orpheus":
        return GroqProviderService.synthesize_orpheus_result(db, text=text, voice=_groq_tts_voice(payload))
    if tts_provider == "cartesia":
        return CartesiaProviderService.synthesize_text_result(db, text=text, voice_id=_demo_tts_voice_id(payload, voice_id) or None)
    if tts_provider == "elevenlabs":
        settings = payload.get("elevenlabs_voice_settings") if isinstance(payload.get("elevenlabs_voice_settings"), dict) else None
        return ElevenLabsProviderService.synthesize_text_result(db, text=text, voice_id=_demo_tts_voice_id(payload, voice_id) or None, voice_settings=settings)
    if streaming_chunk:
        return AzureSpeechProviderService.synthesize_demo_chunk_result(
            db,
            text=text,
            voice_id=voice_id,
            output_format=FAST_DEMO_TTS_FORMAT,
            speaking_rate=speaking_rate,
        )
    return AzureSpeechProviderService.synthesize_text_result(
        db,
        text=text,
        voice_id=voice_id,
        output_format=FAST_DEMO_TTS_FORMAT,
        use_ssml=True,
        speaking_rate=speaking_rate,
    )


def _fallback_reply() -> str:
    return "Sorry, can you repeat that?"


def _retry_empty_llm_once(
    db: Session,
    *,
    provider: str,
    system_prompt: str,
    messages: list[AgentMessage],
    model: str | None,
    tools: list[dict],
) -> str:
    try:
        result = OpenAIProviderService.complete(
            db,
            system_prompt=system_prompt,
            messages=messages,
            model=model,
            tools=tools,
            max_tokens=FAST_DEMO_MAX_TOKENS,
            temperature=FAST_DEMO_TEMPERATURE,
            provider=provider if provider != "openai" else None,
        )
        return str(result.assistant_text or "").strip() or _fallback_reply()
    except Exception:
        logger.exception("demo_empty_llm_retry_failed", extra={"provider": provider})
        return _fallback_reply()


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
    groq_summary = ProviderSettingsService.get_platform_config_admin_view(db, provider="groq")
    deepgram_summary = ProviderSettingsService.get_platform_config_admin_view(db, provider="deepgram")
    cartesia_summary = ProviderSettingsService.get_platform_config_admin_view(db, provider="cartesia")
    elevenlabs_summary = ProviderSettingsService.get_platform_config_admin_view(db, provider="elevenlabs")
    groq_config = groq_summary.get("config") or {}
    deepgram_config = deepgram_summary.get("config") or {}
    cartesia_config = cartesia_summary.get("config") or {}
    elevenlabs_config = elevenlabs_summary.get("config") or {}
    return {
        "providers": {
            "openai": {"configured": True, "voice_mode": "azure_speech_chunks"},
            "deepseek": {
                "configured": bool(deepseek_summary.get("configured") or str(os.getenv("DEEPSEEK_API_KEY") or "").strip()),
                "base_url": str((deepseek_summary.get("config") or {}).get("base_url") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").strip(),
                "model": str((deepseek_summary.get("config") or {}).get("model") or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip(),
                "voice_mode": "azure_speech_chunks",
            },
            "groq": {
                "configured": bool(groq_summary.get("configured") or str(os.getenv("GROQ_API_KEY") or "").strip()),
                "base_url": str(groq_config.get("base_url") or os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai").strip(),
                "stt_model": "whisper-large-v3-turbo",
                "tts_model": str(groq_config.get("tts_model") or groq_config.get("default_tts_model") or os.getenv("GROQ_TTS_MODEL") or "canopylabs/orpheus-v1-english").strip(),
                "tts_voice": _groq_tts_voice({"groq_tts_voice": groq_config.get("tts_voice") or groq_config.get("default_tts_voice") or os.getenv("GROQ_TTS_VOICE")}),
                "voices": sorted(GROQ_ORPHEUS_VOICES),
            },
            "deepgram": {
                "configured": bool(deepgram_summary.get("configured") or str(os.getenv("DEEPGRAM_API_KEY") or "").strip()),
                "model": str(deepgram_config.get("model") or os.getenv("DEEPGRAM_MODEL") or "nova-3").strip(),
                "language": str(deepgram_config.get("language") or os.getenv("DEEPGRAM_LANGUAGE") or "en").strip(),
            },
            "cartesia": {
                "configured": bool(cartesia_summary.get("configured") or str(os.getenv("CARTESIA_API_KEY") or "").strip()),
                "voice_id": str(cartesia_config.get("voice_id") or os.getenv("CARTESIA_VOICE_ID") or "").strip(),
                "model_id": str(cartesia_config.get("model_id") or os.getenv("CARTESIA_MODEL_ID") or "sonic-2").strip(),
            },
            "elevenlabs": {
                "configured": bool(elevenlabs_summary.get("configured")),
                "default_voice_id": str(elevenlabs_config.get("default_voice_id") or elevenlabs_config.get("voice_id") or "").strip(),
                "model_id": str(elevenlabs_config.get("model_id") or "eleven_multilingual_v2").strip(),
                "config": elevenlabs_config,
            },
            "vapi": _vapi_config(db),
        },
        "stt_providers": sorted(DEMO_STT_PROVIDERS),
        "tts_providers": sorted(DEMO_TTS_PROVIDERS),
    }


@admin_router.post("/module-test/stt")
def demo_module_test_stt(
    provider: str = Form("azure_speech"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
):
    selected = _demo_stt_provider(provider)
    if selected == "browser":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Browser STT runs in the browser and has no backend test endpoint")
    audio = file.file.read()
    if not audio:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio file is empty")
    content_type = file.content_type or "audio/webm"
    if selected == "groq":
        result = GroqProviderService.transcribe_audio_result(db, audio=audio, filename=file.filename or "audio.webm", content_type=content_type)
        if not result.get("ok"):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
        return result
    if selected == "deepgram":
        result = DeepgramProviderService.transcribe_audio_result(db, audio=audio, filename=file.filename or "audio.webm", content_type=content_type)
        if not result.get("ok"):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
        return result
    if selected == "elevenlabs":
        result = ElevenLabsProviderService.transcribe_audio_result(db, audio_data=audio, filename=file.filename or "audio.webm", content_type=content_type)
        if not result.get("ok"):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result)
        return result
    try:
        start = time.perf_counter()
        text = AzureSpeechProviderService.transcribe_audio(db, audio=audio, content_type=content_type)
        return {"ok": True, "provider": "azure_speech", "text": text, "language": "en-GB", "timings": {"azure_stt_total_ms": _ms(start)}}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Azure STT failed: {e}") from e


@admin_router.post("/module-test/llm")
def demo_module_test_llm(payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_platform_admin)):
    provider = _demo_provider(payload)
    text = str(payload.get("text") or "Say one short sentence for a voice latency test.").strip()
    if provider == "vapi":
        return {"ok": True, "provider": "vapi", "message": "Vapi is tested through the Vapi browser call, not this LLM-only endpoint."}
    agent = _resolve_demo_agent(db, str(payload.get("agent_slug") or "vox-sales"))
    org_id = str(payload.get("org_id") or "").strip() or _first_org_id_for_user(db, admin.id)
    try:
        result = AgentManager.handle_turn(
            db,
            AgentRunRequest(
                context=AgentRuntimeContext(org_id=org_id, user_id=admin.id, agent_id=agent.id, workflow_type="browser-demo-module-test"),
                latest_user_utterance=text,
                history=[],
                agent_id=agent.id,
            ),
            synthesize_audio=False,
            llm_model=_demo_model_for_provider(provider),
            llm_max_tokens=FAST_DEMO_MAX_TOKENS,
            llm_temperature=FAST_DEMO_TEMPERATURE,
            llm_provider=provider if provider != "openai" else None,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{provider} LLM failed: {e}") from e
    return {"ok": True, "provider": provider, "assistant_text": result.assistant_text, "usage": result.usage}


@admin_router.post("/module-test/tts")
def demo_module_test_tts(payload: dict, db: Session = Depends(get_db), _admin: User = Depends(require_platform_admin)):
    text = str(payload.get("text") or "Hello, this is a quick text to speech test.").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="text is required")
    tts_provider = _demo_tts_provider(payload)
    result = _synthesize_demo_audio(
        db,
        text=text,
        payload=payload,
        voice_id=_demo_voice_id(payload),
        speaking_rate=_demo_speaking_rate(payload),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={k: v for k, v in result.items() if k != "audio_data"})
    audio = bytes(result.get("audio_data") or b"")
    return {
        "ok": True,
        "tts_provider": tts_provider,
        "audio_b64": base64.b64encode(audio).decode("ascii"),
        "audio_mime": result.get("audio_mime") or FAST_DEMO_AUDIO_MIME,
        "audio_bytes": len(audio),
        "voice_id": result.get("voice_id"),
        "model_id": result.get("model_id"),
        "timings": result.get("timings") or {},
    }


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
        if not str(result.assistant_text or "").strip():
            retry_text = _retry_empty_llm_once(
                db,
                provider=provider,
                system_prompt=AgentManager.build_system_prompt(db, agent=agent, context=AgentRuntimeContext(org_id=org_id, user_id=admin.id, agent_id=agent.id, workflow_type="browser-demo")),
                messages=_history_from_payload(payload) + [AgentMessage(role="user", content=user_text)],
                model=selected_model,
                tools=AgentToolRegistry.definitions(
                    allow_lookup=agent.allow_lookup_tool,
                    allow_booking=agent.allow_booking_tool,
                    allow_reschedule=agent.allow_reschedule_tool,
                    allow_cancel=agent.allow_cancel_tool,
                ),
            )
            object.__setattr__(result, "assistant_text", retry_text)
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
        logger.info("demo_azure_tts_end", extra={"agent_slug": agent.slug, "stage_end_ms": tts_end_ms, "azure_tts_ms": tts_ms, "audio_bytes": int(tts.get("audio_bytes") or 0)})
    except Exception as e:
        logger.exception("demo_agent_call_tts_failed", extra={"agent_slug": agent.slug})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{tts_provider} TTS failed: {e}") from e
    if not tts.get("ok"):
        logger.error("demo_agent_call_tts_cancelled", extra={"agent_slug": agent.slug, "error_code": tts.get("error_code"), "error_details": tts.get("error_details")})
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
        "tts_provider": tts_provider,
        "tts_start_ms": tts_start_ms,
        "tts_end_ms": tts_end_ms,
        "tts_ms": tts_ms,
        "response_returned_ms": response_returned_ms,
        "total_roundtrip_ms": response_returned_ms,
        "selected_provider": provider,
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
            "tts_provider": tts_provider,
            "tts_ms": tts_ms,
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
            "tts_provider": tts_provider,
            "voice_id": tts.get("voice_id") or voice_id,
            "output_format": "audio/wav" if tts_provider == "groq_orpheus" else "audio-24khz-160kbitrate-mono-mp3",
            "ssml": None if tts_provider == "groq_orpheus" else f"prosody rate {AzureSpeechProviderService._prosody_rate(speaking_rate)}, pitch default, medium volume, short natural pause",
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
        cartesia_session = None
        cartesia_executor = None
        cartesia_session_future = None

        def disconnected() -> bool:
            try:
                return bool(anyio.from_thread.run(request.is_disconnected))
            except Exception:
                return False

        def emit_tts_events(speakable: str):
            nonlocal audio_index, first_audio_ms, cartesia_session
            tts_start = time.perf_counter()
            if tts_provider == "cartesia":
                if cartesia_session is None:
                    if cartesia_session_future is not None:
                        cartesia_session = cartesia_session_future.result(timeout=10)
                    else:
                        cartesia_session = CartesiaProviderService.realtime_session(db, voice_id=_demo_tts_voice_id(payload, voice_id) or None)
                        cartesia_session.__enter__()
                tts_results = cartesia_session.synthesize_chunks(speakable)
            else:
                tts_results = [
                    _synthesize_demo_audio(
                        db,
                        text=speakable,
                        payload=payload,
                        voice_id=voice_id,
                        speaking_rate=speaking_rate,
                        streaming_chunk=True,
                    )
                ]

            for tts in tts_results:
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
                        "cartesia_ws_first_chunk_ms": tts_timings.get("cartesia_ws_first_chunk_ms"),
                        "cartesia_ws_total_ms": tts_timings.get("cartesia_ws_total_ms"),
                        "elapsed_ms": _ms(total_start),
                        "is_first_audio": audio_index == 1,
                    },
                )

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
            if tts_provider == "cartesia":
                cartesia_config = CartesiaProviderService._config(db)
                cartesia_voice_id = _demo_tts_voice_id(payload, voice_id) or None
                cartesia_executor = ThreadPoolExecutor(max_workers=1)

                def open_cartesia_session():
                    session = CartesiaProviderService.realtime_session_from_config(cartesia_config, voice_id=cartesia_voice_id)
                    session.__enter__()
                    return session

                cartesia_session_future = cartesia_executor.submit(open_cartesia_session)

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
                    force_flush = chunk_buffer_started is not None and (time.perf_counter() - chunk_buffer_started) >= 0.45
                    speakable, chunk_buffer = AzureSpeechProviderService.pop_speakable_chunk(
                        chunk_buffer,
                        force=force_flush,
                        min_words=4 if chunk_index == 0 else 8,
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
                    yield from emit_tts_events(speakable)

            if not assistant_text.strip():
                retry_text = _retry_empty_llm_once(
                    db,
                    provider=provider,
                    system_prompt=system_prompt,
                    messages=messages,
                    model=selected_model,
                    tools=tools,
                )
                assistant_text = retry_text
                chunk_buffer = retry_text
                yield _sse_for(request_id, "llm_text_delta", {"delta": retry_text, "elapsed_ms": _ms(total_start), "fallback": True})

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
                yield from emit_tts_events(speakable)

            yield _sse_for(
                request_id,
                "done",
                {
                    "agent_slug": agent.slug,
                    "agent_text": assistant_text.strip(),
                    "provider": provider,
                    "metrics": {
                        "selected_provider": provider,
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
        finally:
            if cartesia_session is not None:
                cartesia_session.__exit__(None, None, None)
            if cartesia_executor is not None:
                cartesia_executor.shutdown(wait=False, cancel_futures=True)
    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@admin_router.websocket("/stt/deepgram/stream")
async def deepgram_stt_stream(websocket: WebSocket):
    token = websocket.query_params.get("token") or ""
    sessionmaker = get_sessionmaker()
    with sessionmaker() as db:
        try:
            _require_ws_admin(token, db)
            upstream_url, upstream_headers = DeepgramProviderService.websocket_url(db)
        except Exception as exc:
            await websocket.close(code=1008, reason=str(exc)[:120])
            return

    await websocket.accept()
    try:
        async with websockets.connect(upstream_url, additional_headers=upstream_headers) as deepgram_ws:
            await websocket.send_json({"type": "ready", "provider": "deepgram"})

            async def browser_to_deepgram() -> None:
                try:
                    while True:
                        message = await websocket.receive()
                        if message.get("type") == "websocket.disconnect":
                            break
                        if message.get("text") == "close":
                            break
                        data = message.get("bytes")
                        if data:
                            await deepgram_ws.send(data)
                except WebSocketDisconnect:
                    return
                finally:
                    try:
                        await deepgram_ws.close()
                    except Exception:
                        pass

            async def deepgram_to_browser() -> None:
                async for raw in deepgram_ws:
                    event = deepgram_transcript_from_ws_message(raw)
                    if event:
                        await websocket.send_json(event)

            tasks = {
                asyncio.create_task(browser_to_deepgram()),
                asyncio.create_task(deepgram_to_browser()),
            }
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "provider": "deepgram", "message": str(exc)})
        except Exception:
            pass


def _confidence_value(raw: Any) -> float:
    try:
        if raw is None:
            return 1.0
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _word_count(text: str) -> int:
    return len([part for part in str(text or "").split() if part.strip()])


def _pop_realtime_first_chunk(buffer: str) -> tuple[str | None, str]:
    text = str(buffer or "").strip()
    if not text:
        return None, ""
    lowered = text.lower()
    if lowered in {"hello", "yes"}:
        return text, ""
    if lowered.startswith("hello "):
        return text[:5].strip(), text[5:].strip()
    if lowered.startswith("yes "):
        return text[:3].strip(), text[3:].strip()
    for marker in ("hello.", "hello!", "hi.", "hi!", "hi,", "yes,", "yes.", "yes!"):
        if lowered.startswith(marker):
            return text[: len(marker)].strip(), text[len(marker) :].strip()
    if lowered == "hi" or lowered.startswith("hi "):
        return text[:2].strip(), text[2:].strip()
    return None, text


@admin_router.websocket("/voice/realtime")
async def realtime_voice_stream(websocket: WebSocket):
    token = websocket.query_params.get("token") or ""
    sessionmaker = get_sessionmaker()
    with sessionmaker() as db:
        try:
            admin = _require_ws_admin(token, db)
            upstream_url, upstream_headers = DeepgramProviderService.websocket_url(db)
        except Exception as exc:
            await websocket.close(code=1008, reason=str(exc)[:120])
            return

    await websocket.accept()
    outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=2)
    state: dict[str, Any] = {
        "agent_slug": "vox-sales",
        "provider": "groq",
        "tts_provider": "cartesia",
        "cartesia_voice_id": "",
        "voice_id": "",
        "llm_model": "",
        "history": [],
        "turn_active": False,
        "turn_started": False,
        "pending_text": "",
        "speech_started_at": 0.0,
        "audio_started": False,
        "cancel_event": Event(),
        "future": None,
    }

    def emit(payload: dict[str, Any]) -> None:
        if payload.get("type") == "tts_audio_ready" and payload.get("is_first_audio"):
            state["audio_started"] = True
        if payload.get("type") in {"done", "cancelled", "error"}:
            state["turn_active"] = False
        loop.call_soon_threadsafe(outbound.put_nowait, payload)

    def start_turn(text: str, *, reason: str) -> None:
        clean = str(text or "").strip()
        if not clean or state["turn_active"]:
            return
        state["turn_active"] = True
        state["turn_started"] = True
        state["audio_started"] = False
        state["cancel_event"] = Event()
        turn_id = str(uuid4())
        payload = {
            "agent_slug": state["agent_slug"],
            "provider": "groq",
            "tts_provider": "cartesia",
            "cartesia_voice_id": state.get("cartesia_voice_id") or state.get("voice_id") or "",
            "voice_id": state.get("voice_id") or "",
            "llm_model": state.get("llm_model") or "",
            "history": state.get("history") or [],
        }
        emit({"type": "stt_endpoint", "turn_id": turn_id, "text": clean, "reason": reason, "elapsed_ms": 0})
        emit({"type": "llm_start", "turn_id": turn_id, "text": clean, "reason": reason})
        state["future"] = executor.submit(_run_realtime_turn, sessionmaker, str(admin.id), payload, clean, turn_id, state["cancel_event"], emit)

    async def sender() -> None:
        while True:
            payload = await outbound.get()
            await websocket.send_json(payload)

    async def browser_to_deepgram(deepgram_ws) -> None:
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("text"):
                    try:
                        payload = json.loads(message["text"])
                    except Exception:
                        payload = {}
                    kind = payload.get("type")
                    if kind == "start":
                        state.update({k: v for k, v in payload.items() if k in {"agent_slug", "provider", "tts_provider", "cartesia_voice_id", "voice_id", "history", "llm_model"}})
                        emit({"type": "ready", "provider": "dgc_realtime"})
                    elif kind == "cancel":
                        state["cancel_event"].set()
                        state["turn_active"] = False
                        state["turn_started"] = False
                        emit({"type": "cancelled"})
                    elif kind == "audio_playing":
                        emit({
                            "type": "browser_audio_playing",
                            "turn_id": payload.get("turn_id"),
                            "index": payload.get("index"),
                            "browser_at_ms": payload.get("at_ms"),
                        })
                    elif kind == "close":
                        break
                    continue
                data = message.get("bytes")
                if data:
                    await deepgram_ws.send(data)
        except WebSocketDisconnect:
            return
        finally:
            try:
                await deepgram_ws.close()
            except Exception:
                pass

    async def deepgram_to_pipeline(deepgram_ws) -> None:
        async for raw in deepgram_ws:
            event = deepgram_transcript_from_ws_message(raw)
            if not event:
                continue
            text = str(event.get("text") or "").strip()
            confidence = _confidence_value(event.get("confidence"))
            if not text or confidence < 0.4:
                continue
            future = state.get("future")
            if state["turn_active"] and future is not None and future.done():
                state["turn_active"] = False
                state["turn_started"] = False
            emit({"type": "stt_partial" if not (event.get("is_final") or event.get("speech_final")) else "stt_final", **event, "confidence": confidence})
            if not state["speech_started_at"]:
                state["speech_started_at"] = time.perf_counter()
            if state["turn_active"] and state.get("audio_started") and _word_count(text) >= 2:
                state["cancel_event"].set()
                state["turn_active"] = False
                state["turn_started"] = False
                state["pending_text"] = text
                emit({"type": "barge_in", "text": text})
            if state["turn_active"]:
                continue
            should_start_early = confidence >= 0.7 and _word_count(text) >= 4 and not state["turn_started"]
            should_start_final = bool(event.get("speech_final") or event.get("is_final"))
            timed_out = state["speech_started_at"] and (time.perf_counter() - state["speech_started_at"]) >= REALTIME_ENDPOINT_TIMEOUT_SECONDS
            if should_start_early or should_start_final or timed_out:
                state["pending_text"] = text
                state["speech_started_at"] = 0.0
                start_turn(text, reason="partial" if should_start_early and not should_start_final else "final")

    try:
        async with websockets.connect(upstream_url, additional_headers=upstream_headers) as deepgram_ws:
            sender_task = asyncio.create_task(sender())
            tasks = {
                asyncio.create_task(browser_to_deepgram(deepgram_ws)),
                asyncio.create_task(deepgram_to_pipeline(deepgram_ws)),
                sender_task,
            }
            await outbound.put({"type": "connected", "provider": "dgc_realtime"})
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        state["cancel_event"].set()
        executor.shutdown(wait=False, cancel_futures=True)


def _run_realtime_turn(
    sessionmaker,
    admin_id: str,
    payload: dict[str, Any],
    user_text: str,
    turn_id: str,
    cancel_event: Event,
    emit,
) -> None:
    total_start = time.perf_counter()
    first_text_ms: int | None = None
    first_sentence_ms: int | None = None
    first_audio_ms: int | None = None
    first_tts_chunk_sent_ms: int | None = None
    audio_index = 0
    assistant_text = ""
    chunk_buffer = ""
    chunk_buffer_started: float | None = None
    cartesia_session = None
    try:
        with sessionmaker() as db:
            agent = _resolve_demo_agent(db, str(payload.get("agent_slug") or "vox-sales"))
            org_id = str(payload.get("org_id") or "").strip() or None
            if not org_id and admin_id:
                org_id = _first_org_id_for_user(db, admin_id)
            if not org_id:
                org_id = db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
            if not org_id:
                raise ValueError("No organisation exists for realtime agent context")
            workflow_type = "frontpage-talk-to-us" if payload.get("use_agent_config") and payload.get("lead_context") else "browser-demo-realtime"
            context = AgentRuntimeContext(org_id=org_id, user_id=admin_id or None, agent_id=agent.id, workflow_type=workflow_type)
            messages = [AgentMessage(role="user", content=user_text)]
            tools: list[dict[str, Any]] = []
            lead_context = str(payload.get("lead_context") or "").strip()
            if payload.get("use_agent_config"):
                system_prompt = AgentManager.build_system_prompt(
                    db,
                    agent=agent,
                    context=context,
                    extra_context=lead_context or None,
                )
            elif str(payload.get("system_prompt") or "").strip():
                system_prompt = str(payload.get("system_prompt") or "").strip()
            elif str(payload.get("prompt_source") or "").strip() == "frontpage":
                raise ValueError("Frontpage agent prompt is missing. Save a system prompt or Telnyx assistant ID in admin.")
            else:
                system_prompt = REALTIME_SYSTEM_PROMPT
            llm_provider = str(payload.get("provider") or "groq").strip().lower()
            if llm_provider not in {"groq", "deepseek"}:
                llm_provider = "groq"
            requested_model = str(payload.get("llm_model") or "").strip()
            selected_model = requested_model if llm_provider == "groq" and requested_model in REALTIME_GROQ_MODEL_OPTIONS else (REALTIME_GROQ_MODEL if llm_provider == "groq" else None)
            use_frontpage_voice = str(payload.get("prompt_source") or "") == "frontpage"
            if not use_frontpage_voice:
                cartesia_config = CartesiaProviderService._config(db)
                cartesia_open_start = time.perf_counter()
                cartesia_session = CartesiaProviderService.realtime_session_from_config(
                    cartesia_config,
                    voice_id=str(payload.get("cartesia_voice_id") or payload.get("voice_id") or "").strip() or None,
                )
                cartesia_session.__enter__()
                emit({"type": "metrics", "turn_id": turn_id, "cartesia_ws_open_ms": _ms(cartesia_open_start), "cartesia_ws_open_elapsed_ms": _ms(total_start)})

            def emit_tts(speakable: str) -> None:
                nonlocal audio_index, first_audio_ms, first_tts_chunk_sent_ms
                if cancel_event.is_set() or not speakable.strip():
                    return
                tts_start = time.perf_counter()
                if first_tts_chunk_sent_ms is None:
                    first_tts_chunk_sent_ms = _ms(total_start)
                    emit({"type": "metrics", "turn_id": turn_id, "first_tts_chunk_sent_ms": first_tts_chunk_sent_ms})
                if use_frontpage_voice:
                    from app.services.frontpage_voice_service import synthesize_frontpage_voice

                    try:
                        tts = synthesize_frontpage_voice(db, payload, speakable)
                    except Exception as exc:
                        emit({"type": "error", "turn_id": turn_id, "message": f"Voice synthesis failed: {exc}"})
                        return
                    if not tts.get("ok"):
                        emit({"type": "error", "turn_id": turn_id, "message": "Voice synthesis failed", "detail": {k: v for k, v in tts.items() if k != "audio_data"}})
                        return
                    audio_index += 1
                    if first_audio_ms is None:
                        first_audio_ms = _ms(total_start)
                    audio = bytes(tts.get("audio_data") or b"")
                    emit({
                        "type": "tts_audio_ready",
                        "turn_id": turn_id,
                        "index": audio_index,
                        "text": speakable,
                        "tts_provider": str(payload.get("tts_provider") or "telnyx"),
                        "audio_b64": base64.b64encode(audio).decode("ascii"),
                        "audio_mime": tts.get("audio_mime") or "audio/mpeg",
                        "audio_bytes": len(audio),
                        "elapsed_ms": _ms(total_start),
                        "tts_ms": _ms(tts_start),
                        "is_first_audio": audio_index == 1,
                    })
                    return
                for tts in cartesia_session.iter_synthesize_chunks(speakable):
                    if cancel_event.is_set():
                        return
                    if not tts.get("ok"):
                        emit({"type": "error", "turn_id": turn_id, "message": "Cartesia realtime TTS failed", "detail": {k: v for k, v in tts.items() if k != "audio_data"}})
                        return
                    audio_index += 1
                    if first_audio_ms is None:
                        first_audio_ms = _ms(total_start)
                    audio = bytes(tts.get("audio_data") or b"")
                    timings = tts.get("timings") or {}
                    emit({
                        "type": "tts_audio_ready",
                        "turn_id": turn_id,
                        "index": audio_index,
                        "text": speakable,
                        "tts_provider": "cartesia",
                        "audio_b64": base64.b64encode(audio).decode("ascii"),
                        "audio_mime": tts.get("audio_mime") or "audio/wav",
                        "audio_bytes": len(audio),
                        "elapsed_ms": _ms(total_start),
                        "tts_ms": _ms(tts_start),
                        "cartesia_ws_first_chunk_ms": timings.get("cartesia_ws_first_chunk_ms"),
                        "is_first_audio": audio_index == 1,
                    })

            for delta in OpenAIProviderService.stream_complete(
                db,
                system_prompt=system_prompt,
                messages=messages,
                model=selected_model,
                tools=tools,
                max_tokens=REALTIME_MAX_TOKENS,
                temperature=REALTIME_TEMPERATURE,
                provider=llm_provider,
            ):
                if cancel_event.is_set():
                    emit({"type": "cancelled", "turn_id": turn_id})
                    return
                if first_text_ms is None:
                    first_text_ms = _ms(total_start)
                    emit({"type": "metrics", "turn_id": turn_id, "first_llm_token_ms": first_text_ms})
                assistant_text += delta
                if not chunk_buffer.strip():
                    chunk_buffer_started = time.perf_counter()
                chunk_buffer = f"{chunk_buffer}{delta}"
                emit({"type": "llm_text_delta", "turn_id": turn_id, "delta": delta, "elapsed_ms": _ms(total_start)})
                while True:
                    if audio_index == 0:
                        speakable, chunk_buffer = _pop_realtime_first_chunk(chunk_buffer)
                        if not speakable:
                            force_flush = chunk_buffer_started is not None and (time.perf_counter() - chunk_buffer_started) >= 0.08
                            speakable, chunk_buffer = AzureSpeechProviderService.pop_speakable_chunk(chunk_buffer, force=force_flush, min_words=3)
                    else:
                        force_flush = chunk_buffer_started is not None and (time.perf_counter() - chunk_buffer_started) >= 0.35
                        speakable, chunk_buffer = AzureSpeechProviderService.pop_speakable_chunk(chunk_buffer, force=force_flush, min_words=8)
                    if not speakable:
                        break
                    if first_sentence_ms is None:
                        first_sentence_ms = _ms(total_start)
                        emit({"type": "metrics", "turn_id": turn_id, "first_sentence_ready_ms": first_sentence_ms})
                    chunk_buffer_started = time.perf_counter() if chunk_buffer.strip() else None
                    emit({"type": "llm_sentence_ready", "turn_id": turn_id, "text": speakable, "elapsed_ms": _ms(total_start)})
                    emit_tts(speakable)

            if not assistant_text.strip():
                assistant_text = _retry_empty_llm_once(db, provider=llm_provider, system_prompt=system_prompt, messages=messages, model=selected_model, tools=tools)
                chunk_buffer = assistant_text
                emit({"type": "llm_text_delta", "turn_id": turn_id, "delta": assistant_text, "fallback": True, "elapsed_ms": _ms(total_start)})

            while True:
                speakable, chunk_buffer = AzureSpeechProviderService.pop_speakable_chunk(chunk_buffer, final=True)
                if not speakable:
                    break
                if first_sentence_ms is None:
                    first_sentence_ms = _ms(total_start)
                    emit({"type": "metrics", "turn_id": turn_id, "first_sentence_ready_ms": first_sentence_ms})
                emit({"type": "llm_sentence_ready", "turn_id": turn_id, "text": speakable, "elapsed_ms": _ms(total_start)})
                emit_tts(speakable)

            emit({
                "type": "done",
                "turn_id": turn_id,
                "agent_text": assistant_text.strip(),
                "metrics": {
                    "first_text_ms": first_text_ms,
                    "first_sentence_ready_ms": first_sentence_ms,
                    "first_tts_chunk_sent_ms": first_tts_chunk_sent_ms,
                    "first_audio_ms": first_audio_ms,
                    "completed_ms": _ms(total_start),
                    "audio_chunks": audio_index,
                },
            })
    except Exception as exc:
        logger.exception("demo_realtime_turn_failed")
        emit({"type": "error", "turn_id": turn_id, "message": str(exc), "elapsed_ms": _ms(total_start)})
    finally:
        if cartesia_session is not None:
            try:
                cartesia_session.__exit__(None, None, None)
            except Exception:
                pass
