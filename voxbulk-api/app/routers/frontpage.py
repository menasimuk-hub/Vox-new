from __future__ import annotations

import json
import re
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any

import websockets
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin
from app.core.database import get_db, get_sessionmaker
from app.models.agent import AgentDefinition
from app.models.organisation import Organisation
from app.models.frontpage_call_setting import FrontpageCallSetting
from app.models.frontpage_lead_call import FrontpageLeadCall
from app.services.agents.manager import AgentManager
from app.services.frontpage_lead_prompt_generator import generate_frontpage_lead_prompt
from app.services.frontpage_lead_service import (
    apply_lead_intelligence,
    build_runtime_system_prompt,
    combined_lead_transcript,
    enrich_lead_after_transcript_update,
    resolve_frontpage_base_prompt,
    dump_kb_file_ids,
    ensure_recordings_root,
    generate_lead_code,
    lead_source_out,
    parse_kb_file_ids,
    recording_abs_path,
)
from app.services.knowledge_base_service import (
    KB_SCOPE_LEAD,
    KB_SCOPE_SALES,
    build_kb_context_text,
    get_kb_files_by_ids,
    list_kb_files,
    sanitize_kb_file_ids,
)
from app.services.providers.deepgram_service import DeepgramProviderService, deepgram_transcript_from_ws_message
from app.services.telnyx_conversation_service import get_telnyx_media_for_lead, sync_telnyx_lead_artifacts
from app.services.vapi_call_service import get_vapi_media_for_lead
from app.routers.demo import _confidence_value, _run_realtime_turn, _vapi_config, _word_count

router = APIRouter(prefix="/frontpage", tags=["frontpage"])
admin_router = APIRouter(prefix="/admin/frontpage", tags=["admin-frontpage"])

SOURCE = "frontpage_talk_to_us"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
VOICE_PROVIDERS = {"vapi", "telnyx"}


class TalkToUsStartCallIn(BaseModel):
    contact_name: str
    company_name: str
    email: str
    phone: str | None = None
    client_timezone: str | None = None
    client_locale: str | None = None
    client_country: str | None = None
    source: str = SOURCE

    @field_validator("contact_name", "company_name", "email", mode="before")
    @classmethod
    def required_text(cls, value):
        text = str(value or "").strip()
        if not text:
            raise ValueError("This field is required")
        return text

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not EMAIL_RE.match(email):
            raise ValueError("Enter a valid email address")
        return email

    @field_validator("phone", mode="before")
    @classmethod
    def optional_phone(cls, value):
        text = str(value or "").strip()
        return text or None

    @field_validator("source")
    @classmethod
    def valid_source(cls, value: str) -> str:
        if str(value or "").strip() != SOURCE:
            raise ValueError("Invalid source")
        return SOURCE


class FrontpageSettingsIn(BaseModel):
    voice_provider: str = "vapi"
    provider_agent_id: str | None = None
    prompt_description: str | None = None
    system_prompt: str | None = None
    kb_file_ids: list[str] | None = None
    llm_provider: str = "groq"

    @field_validator("voice_provider", mode="before")
    @classmethod
    def clean_voice_provider(cls, value):
        return str(value or "vapi").strip().lower()

    @field_validator("voice_provider")
    @classmethod
    def valid_voice_provider(cls, value: str) -> str:
        if value not in VOICE_PROVIDERS:
            raise ValueError("Voice provider must be vapi or telnyx")
        return value

    @field_validator("provider_agent_id", mode="before")
    @classmethod
    def clean_provider_agent_id(cls, value):
        text = str(value or "").strip()
        return text or None

    @field_validator("llm_provider", mode="before")
    @classmethod
    def clean_llm(cls, value):
        return str(value or "groq").strip().lower()

    @field_validator("llm_provider")
    @classmethod
    def valid_llm(cls, value: str) -> str:
        if value not in {"groq", "deepseek"}:
            raise ValueError("LLM provider must be groq or deepseek")
        return value


class FrontpageImportKbIn(BaseModel):
    kb_file_ids: list[str] = []

    @field_validator("kb_file_ids")
    @classmethod
    def require_files(cls, value: list[str]) -> list[str]:
        ids = [str(v).strip() for v in value if str(v).strip()]
        if not ids:
            raise ValueError("Select at least one knowledge base file")
        return ids


class FrontpageGeneratePromptIn(BaseModel):
    description: str
    kb_file_ids: list[str] = []
    rewrite: bool = True

    @field_validator("description")
    @classmethod
    def valid_description(cls, value: str) -> str:
        text = str(value or "").strip()
        if len(text) < 10:
            raise ValueError("Describe what the lead agent should do (at least 10 characters)")
        return text


class TalkToUsCompleteCallIn(BaseModel):
    transcript_text: str | None = None
    agent_response_text: str | None = None
    duration_seconds: int | None = None
    provider_call_id: str | None = None

    @field_validator("duration_seconds")
    @classmethod
    def valid_duration(cls, value: int | None) -> int | None:
        if value is None:
            return None
        return max(0, int(value))


def _agent_out(agent: AgentDefinition | None) -> dict[str, Any] | None:
    if agent is None:
        return None
    return {"id": agent.id, "name": agent.name, "slug": agent.slug, "is_active": bool(agent.is_active)}


def _default_agent(db: Session) -> AgentDefinition | None:
    rows = list(db.execute(select(AgentDefinition).where(AgentDefinition.is_active.is_(True))).scalars())
    for agent in rows:
        haystack = f"{agent.name} {agent.slug}".lower()
        if "vox" in haystack and ("sales" in haystack or "sale" in haystack):
            return agent
    return rows[0] if rows else None


def _refresh_frontpage_kb(settings: FrontpageCallSetting, db: Session) -> None:
    file_ids = sanitize_kb_file_ids(db, parse_kb_file_ids(settings.kb_file_ids), scope=KB_SCOPE_LEAD)
    settings.kb_file_ids = dump_kb_file_ids(file_ids)
    files = get_kb_files_by_ids(db, file_ids, scope=KB_SCOPE_LEAD) if file_ids else []
    settings.kb_context = build_kb_context_text(files) or None


def _frontpage_sync_prompt(settings: FrontpageCallSetting, *, lead_context: str | None = None) -> str:
    """Telnyx/Vapi runtime: saved system prompt + per-call lead context only (not raw KB files)."""
    base = str(settings.system_prompt or "").strip()
    return build_runtime_system_prompt(
        settings_prompt=base,
        lead_context=lead_context,
        include_kb=False,
    )


def _settings_out(settings: FrontpageCallSetting, agent: AgentDefinition | None = None) -> dict[str, Any]:
    return {
        "voice_provider": settings.voice_provider or "vapi",
        "provider_agent_id": settings.provider_agent_id,
        "prompt_description": settings.prompt_description,
        "system_prompt": settings.system_prompt,
        "kb_file_ids": parse_kb_file_ids(settings.kb_file_ids),
        "kb_context_chars": len(settings.kb_context or ""),
        "llm_provider": settings.llm_provider,
        "updated_at": settings.updated_at,
        "agent": _agent_out(agent),
    }


def _get_settings(db: Session) -> tuple[FrontpageCallSetting, AgentDefinition | None]:
    settings = db.get(FrontpageCallSetting, "default")
    if settings is None:
        agent = _default_agent(db)
        settings = FrontpageCallSetting(
            id="default",
            agent_id=agent.id if agent else None,
            agent_slug=agent.slug if agent else None,
            updated_at=datetime.utcnow(),
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    agent = None
    if settings.agent_id:
        agent = db.execute(select(AgentDefinition).where(AgentDefinition.id == settings.agent_id)).scalar_one_or_none()
    if agent is None and settings.agent_slug:
        agent = db.execute(select(AgentDefinition).where(AgentDefinition.slug == settings.agent_slug)).scalar_one_or_none()
    return settings, agent


def _lead_out(row: FrontpageLeadCall, *, sales_task: dict[str, Any] | None = None) -> dict[str, Any]:
    return lead_source_out(row, sales_task=sales_task)


def _sales_task_out(db: Session, row: Any, *, lead_code: str | None = None) -> dict[str, Any]:
    from app.services.lead_sales_service import get_lead_sales_settings, lead_sales_task_out

    return lead_sales_task_out(row, lead_code=lead_code, settings=get_lead_sales_settings(db))


def _finalize_lead_call(db: Session, lead: FrontpageLeadCall, *, transcript: str, agent_text: str, duration_seconds: int | None) -> FrontpageLeadCall:
    lead.transcript_text = transcript or lead.transcript_text
    lead.agent_response_text = agent_text or lead.agent_response_text
    if duration_seconds is not None:
        lead.duration_seconds = duration_seconds
    lead.status = "completed"
    lead.completed_at = datetime.utcnow()
    db.add(lead)
    db.commit()
    db.refresh(lead)
    enrich_lead_after_transcript_update(db, lead)
    return lead


def background_enrich_telnyx_lead(lead_id: str) -> None:
    """After WebRTC ends, pull official Telnyx transcript then re-extract + sales task."""
    import time

    from app.core.database import get_sessionmaker

    sessionmaker = get_sessionmaker()
    for delay in (8, 20, 45):
        time.sleep(delay)
        with sessionmaker() as db:
            lead = db.get(FrontpageLeadCall, lead_id)
            if lead is None or str(lead.voice_provider or "").strip().lower() != "telnyx":
                return
            before = combined_lead_transcript(lead)
            try:
                sync_telnyx_lead_artifacts(db, lead)
            except Exception:
                continue
            db.refresh(lead)
            after = combined_lead_transcript(lead)
            if after.strip() and (not before.strip() or len(after) > len(before) + 40):
                enrich_lead_after_transcript_update(db, lead)
                return
            if before.strip() and delay >= 20:
                enrich_lead_after_transcript_update(db, lead)
                return


@router.get("/talk-to-us/config")
def get_frontpage_talk_to_us_config(db: Session = Depends(get_db)):
    settings, _ = _get_settings(db)
    voice_provider = settings.voice_provider or "vapi"
    vapi_cfg = _vapi_config(db)
    assistant_id = settings.provider_agent_id or vapi_cfg.get("assistant_id")
    return {
        "voice_provider": voice_provider,
        "provider_agent_id": settings.provider_agent_id,
        "vapi": {
            "configured": bool(vapi_cfg.get("public_key") and assistant_id),
            "public_key": vapi_cfg.get("public_key"),
            "assistant_id": assistant_id,
        },
        "telnyx": {
            "configured": voice_provider == "telnyx"
            and bool(settings.provider_agent_id)
            and bool(str(settings.system_prompt or "").strip()),
            "agent_id": settings.provider_agent_id if voice_provider == "telnyx" else None,
        },
    }


def _lead_runtime_prompt(
    db: Session,
    settings: FrontpageCallSetting,
    payload: TalkToUsStartCallIn,
    agent: AgentDefinition | None = None,
    *,
    phone_e164: str | None = None,
    phone_raw: str | None = None,
    location: Any | None = None,
) -> dict[str, Any]:
    from app.services.telnyx_lead_variables import enrich_lead_context_text

    display_phone = phone_e164 or payload.phone
    lead_context = AgentManager.format_lead_context(
        contact_name=payload.contact_name,
        company_name=payload.company_name,
        email=payload.email,
        phone=display_phone,
    )
    if location is not None:
        lead_context = enrich_lead_context_text(
            lead_context,
            location=location,
            phone_e164=phone_e164,
            phone_raw=str(phone_raw or payload.phone or ""),
        )
    base_prompt = resolve_frontpage_base_prompt(db, settings=settings, agent=agent)
    system_prompt = build_runtime_system_prompt(
        settings_prompt=base_prompt,
        lead_context=lead_context,
        include_kb=False,
    )
    first_name = str(payload.contact_name or "").strip().split()[0] if payload.contact_name else "there"
    return {
        "assistant_id": settings.provider_agent_id,
        "system_prompt": system_prompt,
        "variable_values": {
            "contact_name": payload.contact_name,
            "company_name": payload.company_name,
            "email": payload.email,
            "phone": display_phone or "",
            "phone_raw": str(phone_raw or payload.phone or ""),
            "country": getattr(location, "country", "") if location else "",
            "country_code": getattr(location, "country_code", "") if location else "",
            "timezone": getattr(location, "timezone", "") if location else "",
            "locale": getattr(location, "locale", "") if location else "",
        },
        "first_message": _intake_call_opening_greeting(first_name, system_prompt),
    }


def _intake_call_opening_greeting(first_name: str, system_prompt: str) -> str:
    """First line the intake agent speaks as soon as the browser call connects."""
    from app.services.telnyx_assistant_service import derive_greeting_from_prompt

    first = str(first_name or "").strip() or "there"
    derived = derive_greeting_from_prompt(system_prompt)
    if derived:
        line = derived.replace("Hi there,", f"Hi {first},").replace("Hi there", f"Hi {first}")
    else:
        line = f"Hi {first}, thanks for contacting VOXBULK. How can I help you today?"
    if "recorded" not in line.lower():
        line = f"{line} This call is recorded for quality — see voxbulk.com for privacy."
    return line


def _vapi_runtime_for_lead(
    db: Session,
    settings: FrontpageCallSetting,
    payload: TalkToUsStartCallIn,
    agent: AgentDefinition | None = None,
) -> dict[str, Any]:
    return _lead_runtime_prompt(db, settings, payload, agent)


@router.post("/talk-to-us/start-call")
def start_frontpage_talk_to_us_call(
    payload: TalkToUsStartCallIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    settings, agent = _get_settings(db)
    voice_provider = (settings.voice_provider or "vapi").strip().lower()
    if voice_provider not in VOICE_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Lead voice provider is not configured")
    if not settings.provider_agent_id:
        label = "Vapi assistant ID" if voice_provider == "vapi" else "Telnyx assistant ID"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Lead voice agent is not configured yet. Save your {label} in admin → Front page call leads.",
        )
    if voice_provider == "telnyx":
        base_prompt = resolve_frontpage_base_prompt(db, settings=settings, agent=agent)
        if not base_prompt:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Save a system prompt in admin → Front page call leads.",
            )
    else:
        vapi_cfg = _vapi_config(db)
        if not vapi_cfg.get("public_key"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Vapi public key is missing. Add it under Integrations → Vapi.",
            )
    from app.services.telnyx_lead_variables import (
        build_telnyx_custom_headers,
        ensure_telnyx_variables_block,
        normalize_lead_phone,
        resolve_lead_location,
    )

    location = resolve_lead_location(
        phone=payload.phone,
        client_timezone=payload.client_timezone,
        client_locale=payload.client_locale,
        client_country=payload.client_country,
    )
    phone_e164, phone_raw = normalize_lead_phone(payload.phone, location)

    lead_call = FrontpageLeadCall(
        lead_code=generate_lead_code(),
        contact_name=payload.contact_name,
        company_name=payload.company_name,
        email=payload.email,
        phone=phone_e164 or payload.phone,
        source=SOURCE,
        status="created",
        voice_provider=settings.voice_provider,
        provider_agent_id=settings.provider_agent_id,
    )
    db.add(lead_call)
    lead_call.status = "started"
    lead_call.started_at = datetime.utcnow()
    db.commit()
    db.refresh(lead_call)
    response: dict[str, Any] = {
        "call_id": lead_call.id,
        "lead_code": lead_call.lead_code,
        "status": lead_call.status,
        "voice_provider": lead_call.voice_provider,
    }
    if voice_provider == "telnyx":
        runtime = _lead_runtime_prompt(
            db,
            settings,
            payload,
            agent,
            phone_e164=phone_e164,
            phone_raw=phone_raw,
            location=location,
        )
        try:
            from app.services.telnyx_assistant_service import prepare_telnyx_webrtc_call

            telnyx_prompt = ensure_telnyx_variables_block(str(runtime["system_prompt"]))
            first_message = str(runtime.get("first_message") or "").strip()
            prep = prepare_telnyx_webrtc_call(
                db,
                str(settings.provider_agent_id or ""),
                telnyx_prompt,
                greeting=first_message or None,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        custom_headers = build_telnyx_custom_headers(
            call_id=lead_call.id,
            contact_name=payload.contact_name,
            company_name=payload.company_name,
            email=payload.email,
            phone_e164=phone_e164,
            phone_raw=phone_raw,
            location=location,
        )
        response["telnyx"] = {
            "configured": True,
            "agent_id": prep["assistant_id"],
            "web_calls_enabled": True,
            "prompt_synced": bool(prep.get("prompt_synced")),
            "first_message": first_message,
            "recording_channels": prep.get("recording_channels", "dual"),
            "custom_headers": custom_headers,
            "phone_e164": phone_e164,
            "country": location.country,
            "country_code": location.country_code,
        }
        response["vapi"] = {"configured": False}
    else:
        vapi_cfg = _vapi_config(db)
        response["vapi"] = {
            "public_key": vapi_cfg.get("public_key"),
            "configured": bool(vapi_cfg.get("public_key") and settings.provider_agent_id),
            **_vapi_runtime_for_lead(db, settings, payload, agent),
        }
        response["telnyx"] = {"configured": False}
    return response


@router.post("/talk-to-us/complete-call/{call_id}")
async def complete_frontpage_talk_to_us_call(
    call_id: str,
    background_tasks: BackgroundTasks,
    transcript_text: str | None = Form(default=None),
    agent_response_text: str | None = Form(default=None),
    duration_seconds: int | None = Form(default=None),
    provider_call_id: str | None = Form(default=None),
    recording: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    lead = db.get(FrontpageLeadCall, call_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    if transcript_text:
        lead.transcript_text = transcript_text.strip()
    if agent_response_text:
        lead.agent_response_text = agent_response_text.strip()
    if provider_call_id:
        lead.provider_call_id = provider_call_id.strip()

    if recording is not None and recording.filename:
        ensure_recordings_root()
        ext = ".webm"
        if recording.filename and "." in recording.filename:
            ext = "." + recording.filename.rsplit(".", 1)[-1].lower()[:8]
        rel = f"data/frontpage-recordings/{lead.id}{ext}"
        abs_path = recording_abs_path(rel)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        raw = await recording.read()
        if raw:
            abs_path.write_bytes(raw)
            lead.recording_path = rel.replace("\\", "/")

    lead = _finalize_lead_call(
        db,
        lead,
        transcript=str(lead.transcript_text or ""),
        agent_text=str(lead.agent_response_text or ""),
        duration_seconds=duration_seconds,
    )
    if str(lead.voice_provider or "").strip().lower() == "telnyx":
        background_tasks.add_task(background_enrich_telnyx_lead, lead.id)
    return {"ok": True, "lead": _lead_out(lead)}


@router.post("/talk-to-us/complete-call/{call_id}/json")
def complete_frontpage_talk_to_us_call_json(
    call_id: str,
    payload: TalkToUsCompleteCallIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    lead = db.get(FrontpageLeadCall, call_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")
    if payload.transcript_text:
        lead.transcript_text = payload.transcript_text.strip()
    if payload.agent_response_text:
        lead.agent_response_text = payload.agent_response_text.strip()
    if payload.provider_call_id:
        lead.provider_call_id = payload.provider_call_id.strip()
    lead = _finalize_lead_call(
        db,
        lead,
        transcript=str(lead.transcript_text or ""),
        agent_text=str(lead.agent_response_text or ""),
        duration_seconds=payload.duration_seconds,
    )
    if str(lead.voice_provider or "").strip().lower() == "telnyx":
        background_tasks.add_task(background_enrich_telnyx_lead, lead.id)
    return {"ok": True, "lead": _lead_out(lead)}


@router.websocket("/talk-to-us/voice/{call_id}")
async def frontpage_talk_to_us_voice(websocket: WebSocket, call_id: str):
    await websocket.accept()
    sessionmaker = get_sessionmaker()

    with sessionmaker() as db:
        lead = db.get(FrontpageLeadCall, call_id)
        if lead is None:
            await websocket.send_json({"type": "error", "message": "Call not found"})
            await websocket.close(code=1008)
            return
        settings, agent = _get_settings(db)
        if (settings.voice_provider or "vapi") == "vapi":
            await websocket.send_json({"type": "error", "message": "This call uses Vapi in the browser. Connect with the Vapi client instead."})
            await websocket.close(code=1008)
            return
        if (settings.voice_provider or "vapi") == "telnyx":
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Telnyx uses WebRTC in the browser (not this server voice socket). Refresh the page and try Talk to us again.",
                }
            )
            await websocket.close(code=1008)
            return

    outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=2)

    with sessionmaker() as db:
        lead = db.get(FrontpageLeadCall, call_id)
        settings, agent = _get_settings(db)
        lead_context = AgentManager.format_lead_context(
            contact_name=lead.contact_name,
            company_name=lead.company_name,
            email=lead.email,
            phone=lead.phone,
        )
        telnyx_runtime: dict[str, Any] = {}
        provider_agent_id = str(settings.provider_agent_id or "").strip()
        if provider_agent_id:
            try:
                from app.services.telnyx_assistant_service import resolve_telnyx_assistant_runtime

                telnyx_runtime = resolve_telnyx_assistant_runtime(db, provider_agent_id)
            except Exception:
                telnyx_runtime = {}
        base_prompt = resolve_frontpage_base_prompt(db, settings=settings, agent=agent)
        system_prompt = build_runtime_system_prompt(
            settings_prompt=base_prompt,
            lead_context=lead_context,
            include_kb=False,
        )
        if not str(base_prompt or "").strip():
            await websocket.send_json({"type": "error", "message": "Agent prompt is not configured. Save a system prompt or Telnyx assistant ID in admin."})
            await websocket.close(code=1008)
            return
        org_id = settings.org_id or db.execute(select(Organisation.id).order_by(Organisation.created_at.asc()).limit(1)).scalar_one_or_none()
        upstream_url, upstream_headers = DeepgramProviderService.websocket_url(db)
        agent_slug = str(settings.agent_slug or (agent.slug if agent else "") or "vox-sales").strip()
        tts_provider = str(telnyx_runtime.get("tts_provider") or settings.tts_provider or "telnyx").strip().lower()
        realtime_payload = {
            "agent_slug": agent_slug,
            "provider": settings.llm_provider,
            "tts_provider": tts_provider,
            "telnyx_voice": str(telnyx_runtime.get("voice") or "").strip(),
            "telnyx_voice_speed": telnyx_runtime.get("voice_speed"),
            "elevenlabs_voice_id": str(telnyx_runtime.get("elevenlabs_voice_id") or "").strip(),
            "elevenlabs_voice_settings": telnyx_runtime.get("elevenlabs_voice_settings") or {},
            "greeting": str(telnyx_runtime.get("greeting") or "").strip(),
            "assistant_name": str(telnyx_runtime.get("assistant_name") or "").strip(),
            "history": [],
            "use_agent_config": False,
            "system_prompt": system_prompt,
            "lead_context": lead_context,
            "org_id": org_id,
            "prompt_source": "frontpage",
        }

    state: dict[str, Any] = {
        "turn_active": False,
        "turn_started": False,
        "speech_started_at": 0.0,
        "audio_started": False,
        "cancel_event": Event(),
        "future": None,
    }

    def persist_update(**values) -> None:
        with sessionmaker() as db:
            row = db.get(FrontpageLeadCall, call_id)
            if row is None:
                return
            for key, value in values.items():
                setattr(row, key, value)
            db.add(row)
            db.commit()

    def append_transcript(text: str) -> None:
        clean = str(text or "").strip()
        if not clean:
            return
        with sessionmaker() as db:
            row = db.get(FrontpageLeadCall, call_id)
            if row is None:
                return
            existing = str(row.transcript_text or "").strip()
            if clean not in existing:
                row.transcript_text = f"{existing}\nUser: {clean}".strip()
                db.add(row)
                db.commit()

    def emit(payload: dict[str, Any]) -> None:
        if payload.get("type") == "tts_audio_ready" and payload.get("is_first_audio"):
            state["audio_started"] = True
        if payload.get("type") == "done":
            state["turn_active"] = False
            agent_text = str(payload.get("agent_text") or "").strip()
            if agent_text:
                with sessionmaker() as db:
                    row = db.get(FrontpageLeadCall, call_id)
                    if row is not None:
                        existing = str(row.agent_response_text or "").strip()
                        row.agent_response_text = f"{existing}\nAgent: {agent_text}".strip()
                        db.add(row)
                        db.commit()
        if payload.get("type") in {"cancelled", "error"}:
            state["turn_active"] = False
        loop.call_soon_threadsafe(outbound.put_nowait, payload)

    def start_turn(text: str, *, reason: str) -> None:
        clean = str(text or "").strip()
        if not clean or state["turn_active"]:
            return
        append_transcript(clean)
        state["turn_active"] = True
        state["turn_started"] = True
        state["audio_started"] = False
        state["cancel_event"] = Event()
        turn_id = f"{call_id}-{int(datetime.utcnow().timestamp() * 1000)}"
        emit({"type": "llm_start", "turn_id": turn_id, "text": clean, "reason": reason})
        state["future"] = executor.submit(_run_realtime_turn, sessionmaker, "", realtime_payload, clean, turn_id, state["cancel_event"], emit)

    async def sender() -> None:
        while True:
            await websocket.send_json(await outbound.get())

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
                    if payload.get("type") == "close":
                        break
                    if payload.get("type") == "cancel":
                        state["cancel_event"].set()
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
            emit({"type": "stt_partial" if not (event.get("is_final") or event.get("speech_final")) else "stt_final", **event, "confidence": confidence})
            if not state["speech_started_at"]:
                state["speech_started_at"] = datetime.utcnow().timestamp()
            if state["turn_active"] and state.get("audio_started") and _word_count(text) >= 2:
                state["cancel_event"].set()
                state["turn_active"] = False
                emit({"type": "barge_in", "text": text})
            if state["turn_active"]:
                continue
            elapsed = datetime.utcnow().timestamp() - float(state["speech_started_at"] or 0)
            should_start_early = confidence >= 0.7 and _word_count(text) >= 4 and not state["turn_started"]
            should_start_final = bool(event.get("speech_final") or event.get("is_final"))
            if should_start_early or should_start_final or elapsed >= 1.0:
                state["speech_started_at"] = 0.0
                start_turn(text, reason="partial" if should_start_early and not should_start_final else "final")

    try:
        persist_update(status="in_call", started_at=datetime.utcnow())
        await outbound.put({"type": "connected", "provider": "telnyx_assistant", "call_id": call_id})
        greeting = str(realtime_payload.get("greeting") or "").strip()
        if greeting:
            import base64

            from app.services.frontpage_voice_service import synthesize_frontpage_voice

            with sessionmaker() as db:
                tts = synthesize_frontpage_voice(db, realtime_payload, greeting)
            if tts.get("ok"):
                await outbound.put(
                    {
                        "type": "tts_audio_ready",
                        "turn_id": f"{call_id}-greeting",
                        "text": greeting,
                        "tts_provider": realtime_payload.get("tts_provider"),
                        "audio_b64": base64.b64encode(bytes(tts.get("audio_data") or b"")).decode("ascii"),
                        "audio_mime": tts.get("audio_mime") or "audio/mpeg",
                        "is_first_audio": True,
                    }
                )
                with sessionmaker() as db:
                    row = db.get(FrontpageLeadCall, call_id)
                    if row is not None:
                        row.agent_response_text = f"Agent: {greeting}"
                        db.add(row)
                        db.commit()
        await outbound.put(
            {
                "type": "ready",
                "provider": "telnyx_assistant",
                "assistant_name": realtime_payload.get("assistant_name"),
                "voice": realtime_payload.get("telnyx_voice"),
            }
        )
        async with websockets.connect(upstream_url, additional_headers=upstream_headers) as deepgram_ws:
            tasks = {
                asyncio.create_task(sender()),
                asyncio.create_task(browser_to_deepgram(deepgram_ws)),
                asyncio.create_task(deepgram_to_pipeline(deepgram_ws)),
            }
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except Exception as exc:
        persist_update(status="failed", failed_at=datetime.utcnow(), last_error=str(exc)[:500])
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        state["cancel_event"].set()
        executor.shutdown(wait=False, cancel_futures=True)


@admin_router.get("/talk-to-us")
def get_frontpage_talk_to_us_admin(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    settings, agent = _get_settings(db)
    kb_files = list_kb_files(db, scope=KB_SCOPE_LEAD)
    return {
        "settings": _settings_out(settings, agent),
        "kb_files": kb_files,
    }


@admin_router.put("/talk-to-us/settings")
def update_frontpage_talk_to_us_settings(payload: FrontpageSettingsIn, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    settings, agent = _get_settings(db)
    voice_provider = (payload.voice_provider or "vapi").strip().lower()
    if not payload.provider_agent_id:
        label = "Vapi assistant ID" if voice_provider == "vapi" else "Telnyx assistant ID"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label} is required")
    effective_prompt = payload.system_prompt if payload.system_prompt is not None else settings.system_prompt
    effective_agent_id = payload.provider_agent_id or settings.provider_agent_id
    if voice_provider == "telnyx":
        if not str(effective_agent_id or "").strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Telnyx assistant ID is required.")
        if not str(effective_prompt or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="System prompt is required. It will be synced to your Telnyx assistant on save.",
            )
    settings.voice_provider = payload.voice_provider
    settings.provider_agent_id = payload.provider_agent_id
    settings.prompt_description = (payload.prompt_description or "").strip() or None
    if payload.system_prompt is not None:
        settings.system_prompt = payload.system_prompt.strip() or None
    if payload.kb_file_ids is not None:
        clean_ids = sanitize_kb_file_ids(db, payload.kb_file_ids, scope=KB_SCOPE_LEAD)
        settings.kb_file_ids = dump_kb_file_ids(clean_ids)
    settings.llm_provider = payload.llm_provider
    settings.updated_at = datetime.utcnow()
    _refresh_frontpage_kb(settings, db)
    db.add(settings)
    db.commit()
    telnyx_sync = None
    telnyx_sync_warning = None
    if voice_provider == "telnyx" and effective_agent_id and str(effective_prompt or "").strip():
        try:
            from app.services.telnyx_assistant_service import sync_telnyx_assistant_instructions
            from app.services.telnyx_lead_variables import ensure_telnyx_variables_block

            sync_prompt = ensure_telnyx_variables_block(_frontpage_sync_prompt(settings))
            if not sync_prompt.strip():
                raise ValueError("System prompt is empty after merging knowledge base.")
            telnyx_sync = sync_telnyx_assistant_instructions(db, effective_agent_id, sync_prompt)
        except Exception as exc:
            telnyx_sync_warning = str(exc)
    db.refresh(settings)
    return {
        "settings": _settings_out(settings, agent),
        "telnyx_synced": bool(telnyx_sync),
        "telnyx_sync_warning": telnyx_sync_warning,
    }


@admin_router.post("/talk-to-us/import-kb-prompt")
def import_frontpage_prompt_from_kb(
    payload: FrontpageImportKbIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    from app.services.knowledge_base_service import compose_prompt_from_kb_files, get_kb_files_by_ids

    settings, agent = _get_settings(db)
    clean_ids = sanitize_kb_file_ids(db, payload.kb_file_ids, scope=KB_SCOPE_LEAD)
    files = get_kb_files_by_ids(db, clean_ids, scope=KB_SCOPE_LEAD)
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected knowledge base files were not found")
    prompt = compose_prompt_from_kb_files(files)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected files are empty")
    settings.system_prompt = prompt
    settings.kb_file_ids = dump_kb_file_ids(clean_ids)
    settings.updated_at = datetime.utcnow()
    _refresh_frontpage_kb(settings, db)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return {
        "system_prompt": prompt,
        "kb_file_ids": parse_kb_file_ids(settings.kb_file_ids),
        "kb_files_used": [f.original_filename for f in files],
        "prompt_chars": len(prompt),
        "imported_verbatim": True,
        "settings": _settings_out(settings, agent),
    }


@admin_router.post("/talk-to-us/generate-prompt")
def generate_frontpage_lead_agent_prompt(payload: FrontpageGeneratePromptIn, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    settings, agent = _get_settings(db)
    if not payload.rewrite and settings.system_prompt:
        _refresh_frontpage_kb(settings, db)
        return {
            "system_prompt": settings.system_prompt,
            "skipped": True,
            "kb_file_ids": parse_kb_file_ids(settings.kb_file_ids),
            "kb_context_chars": len(settings.kb_context or ""),
        }
    clean_ids = sanitize_kb_file_ids(db, payload.kb_file_ids, scope=KB_SCOPE_LEAD)
    files = get_kb_files_by_ids(db, clean_ids, scope=KB_SCOPE_LEAD)
    if payload.kb_file_ids and not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected knowledge base files were not found. Refresh the page and tick your lead KB files again.",
        )
    try:
        prompt = generate_frontpage_lead_prompt(db, description=payload.description, knowledge_files=files)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Prompt generation failed: {e}") from e
    settings.prompt_description = payload.description
    settings.system_prompt = prompt
    settings.kb_file_ids = dump_kb_file_ids(clean_ids)
    settings.updated_at = datetime.utcnow()
    _refresh_frontpage_kb(settings, db)
    db.add(settings)
    db.commit()
    return {
        "system_prompt": prompt,
        "kb_file_ids": parse_kb_file_ids(settings.kb_file_ids),
        "kb_files_used": [f.original_filename for f in files],
        "kb_context_chars": len(settings.kb_context or ""),
        "prompt_chars": len(prompt),
    }


@admin_router.get("/lead-sources")
def list_lead_sources(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask
    from app.services.lead_sales_service import sales_task_brief

    rows = list(
        db.execute(
            select(FrontpageLeadCall)
            .where(FrontpageLeadCall.status == "completed")
            .order_by(FrontpageLeadCall.completed_at.desc(), FrontpageLeadCall.created_at.desc())
            .limit(500)
        ).scalars()
    )
    lead_ids = [row.id for row in rows]
    tasks_by_lead: dict[str, LeadSalesTask] = {}
    if lead_ids:
        for task in db.execute(select(LeadSalesTask).where(LeadSalesTask.lead_id.in_(lead_ids))).scalars():
            tasks_by_lead[task.lead_id] = task
    return {
        "leads": [
            _lead_out(row, sales_task=sales_task_brief(tasks_by_lead.get(row.id)))
            for row in rows
        ]
    }


@admin_router.get("/lead-sources/export")
def export_lead_sources_csv(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from fastapi.responses import Response

    from app.models.lead_sales_task import LeadSalesTask
    from app.services.csv_export_service import lead_sources_csv

    rows = list(
        db.execute(
            select(FrontpageLeadCall)
            .where(FrontpageLeadCall.status == "completed")
            .order_by(FrontpageLeadCall.completed_at.desc(), FrontpageLeadCall.created_at.desc())
            .limit(500)
        ).scalars()
    )
    lead_ids = [row.id for row in rows]
    tasks_by_lead: dict[str, LeadSalesTask] = {}
    if lead_ids:
        for task in db.execute(select(LeadSalesTask).where(LeadSalesTask.lead_id.in_(lead_ids))).scalars():
            tasks_by_lead[task.lead_id] = task
    body, filename = lead_sources_csv(rows, tasks_by_lead=tasks_by_lead)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_router.get("/lead-sources/{lead_id}")
def get_lead_source(lead_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    row = db.get(FrontpageLeadCall, lead_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    vapi = None
    telnyx = None
    provider = str(row.voice_provider or "").strip().lower()
    if provider == "vapi":
        vapi = get_vapi_media_for_lead(db, row)
        if vapi.get("transcript"):
            row.transcript_text = vapi["transcript"]
            row.agent_response_text = None
            db.commit()
            db.refresh(row)
    elif provider == "telnyx":
        try:
            telnyx = get_telnyx_media_for_lead(db, row)
            if telnyx.get("transcript"):
                row.transcript_text = telnyx["transcript"]
                row.agent_response_text = None
            conversation_id = str(telnyx.get("conversation_id") or "").strip()
            if conversation_id:
                row.provider_call_id = conversation_id
            if telnyx.get("transcript") or conversation_id:
                db.commit()
                db.refresh(row)
        except Exception as exc:
            telnyx = {
                "source": "telnyx",
                "available": False,
                "error": f"Telnyx media load failed: {exc}",
                "messages": [],
            }
    return {"lead": _lead_out(row), "vapi": vapi, "telnyx": telnyx}


@admin_router.post("/lead-sources/{lead_id}/sync-vapi")
def sync_lead_source_vapi(lead_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    row = db.get(FrontpageLeadCall, lead_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    vapi = get_vapi_media_for_lead(db, row)
    if vapi.get("transcript"):
        row.transcript_text = vapi["transcript"]
        row.agent_response_text = None
        db.commit()
        db.refresh(row)
    if vapi.get("error") and not vapi.get("available"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=vapi["error"])
    return {"lead": _lead_out(row), "vapi": vapi}


@admin_router.post("/lead-sources/{lead_id}/sync-telnyx")
def sync_lead_source_telnyx(lead_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    row = db.get(FrontpageLeadCall, lead_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    if str(row.voice_provider or "").strip().lower() != "telnyx":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a Telnyx lead")
    sync_result = sync_telnyx_lead_artifacts(db, row)
    db.refresh(row)
    if sync_result.get("transcript_updated") or combined_lead_transcript(row).strip():
        enrich_lead_after_transcript_update(db, row)
        db.refresh(row)
    telnyx = get_telnyx_media_for_lead(db, row)
    if sync_result.get("error") and not telnyx.get("available"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=sync_result["error"])
    return {"lead": _lead_out(row), "telnyx": telnyx, "sync": sync_result}


@admin_router.get("/lead-sources/{lead_id}/recording")
def get_lead_source_recording(lead_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    """Telnyx: stream dual-channel WAV from Telnyx API. Vapi: redirect to hosted URL. Else: local file."""
    row = db.get(FrontpageLeadCall, lead_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    provider = str(row.voice_provider or "").strip().lower()

    if provider == "telnyx":
        from app.services.telnyx_conversation_service import telnyx_recording_response

        stream, err = telnyx_recording_response(db, row)
        if stream is not None:
            return stream
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err or "No Telnyx dual recording yet. Wait a minute after the call ends, then refresh.",
        )

    if row.recording_path:
        path = recording_abs_path(row.recording_path)
        if path.is_file():
            media = "audio/webm"
            if path.suffix.lower() in {".wav"}:
                media = "audio/wav"
            elif path.suffix.lower() in {".mp3", ".mpeg"}:
                media = "audio/mpeg"
            return FileResponse(path, media_type=media, filename=path.name)

    if provider == "vapi":
        vapi = get_vapi_media_for_lead(db, row)
        remote_url = str(vapi.get("recording_url") or "").strip()
        if remote_url:
            return RedirectResponse(url=remote_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=vapi.get("error")
            or "No Vapi recording URL yet. Enable recording on the assistant in Vapi, then refresh.",
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No recording for this lead yet.",
    )


class LeadSalesSettingsIn(BaseModel):
    telnyx_assistant_id: str | None = None
    prompt_description: str | None = None
    system_prompt: str | None = None
    kb_file_ids: list[str] | None = None
    calling_hour_start: int | None = None
    calling_hour_end: int | None = None
    calling_days: str | None = None

    @field_validator("telnyx_assistant_id", mode="before")
    @classmethod
    def clean_assistant_id(cls, value):
        text = str(value or "").strip()
        return text or None


class LeadSalesImportKbIn(BaseModel):
    kb_file_ids: list[str] = []

    @field_validator("kb_file_ids")
    @classmethod
    def require_files(cls, value: list[str]) -> list[str]:
        ids = [str(v).strip() for v in value if str(v).strip()]
        if not ids:
            raise ValueError("Select at least one knowledge base file")
        return ids


class LeadSalesGeneratePromptIn(BaseModel):
    description: str
    kb_file_ids: list[str] = []
    rewrite: bool = True


@admin_router.get("/lead-sales/settings")
def get_lead_sales_settings_route(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.services.lead_sales_service import get_lead_sales_settings, lead_sales_settings_out
    from app.services.knowledge_base_service import list_kb_files

    row = get_lead_sales_settings(db)
    return {"settings": lead_sales_settings_out(row), "kb_files": list_kb_files(db, scope=KB_SCOPE_SALES)}


@admin_router.put("/lead-sales/settings")
def update_lead_sales_settings_route(
    payload: LeadSalesSettingsIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    from app.services.frontpage_lead_service import dump_kb_file_ids
    from app.services.lead_sales_service import get_lead_sales_settings, lead_sales_settings_out, refresh_lead_sales_kb

    row = get_lead_sales_settings(db)
    if payload.telnyx_assistant_id is not None:
        row.telnyx_assistant_id = payload.telnyx_assistant_id
    if payload.prompt_description is not None:
        row.prompt_description = str(payload.prompt_description or "").strip() or None
    if payload.system_prompt is not None:
        row.system_prompt = str(payload.system_prompt or "").strip() or None
    if payload.kb_file_ids is not None:
        clean_ids = sanitize_kb_file_ids(db, payload.kb_file_ids, scope=KB_SCOPE_SALES)
        row.kb_file_ids = dump_kb_file_ids(clean_ids)
    if payload.calling_hour_start is not None:
        row.calling_hour_start = int(payload.calling_hour_start)
    if payload.calling_hour_end is not None:
        row.calling_hour_end = int(payload.calling_hour_end)
    if payload.calling_days is not None:
        row.calling_days = str(payload.calling_days or "1,2,3,4,5").strip()
    row.updated_at = datetime.utcnow()
    refresh_lead_sales_kb(row, db)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"settings": lead_sales_settings_out(row)}


@admin_router.post("/lead-sales/import-kb-prompt")
def import_lead_sales_prompt_from_kb(
    payload: LeadSalesImportKbIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    from app.services.knowledge_base_service import compose_prompt_from_kb_files, get_kb_files_by_ids
    from app.services.lead_sales_service import get_lead_sales_settings, lead_sales_settings_out, refresh_lead_sales_kb
    from app.services.frontpage_lead_service import dump_kb_file_ids

    settings = get_lead_sales_settings(db)
    clean_ids = sanitize_kb_file_ids(db, payload.kb_file_ids, scope=KB_SCOPE_SALES)
    files = get_kb_files_by_ids(db, clean_ids, scope=KB_SCOPE_SALES)
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected knowledge base files were not found")
    prompt = compose_prompt_from_kb_files(files)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected files are empty")
    settings.system_prompt = prompt
    settings.kb_file_ids = dump_kb_file_ids(clean_ids)
    settings.updated_at = datetime.utcnow()
    refresh_lead_sales_kb(settings, db)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return {
        "system_prompt": prompt,
        "kb_files_used": [f.original_filename for f in files],
        "prompt_chars": len(prompt),
        "imported_verbatim": True,
        "settings": lead_sales_settings_out(settings),
    }


@admin_router.post("/lead-sales/generate-prompt")
def generate_lead_sales_master_prompt_route(
    payload: LeadSalesGeneratePromptIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    from app.services.knowledge_base_service import get_kb_files_by_ids
    from app.services.lead_sales_master_prompt_generator import generate_lead_sales_master_prompt
    from app.services.lead_sales_service import get_lead_sales_settings, lead_sales_settings_out, refresh_lead_sales_kb
    from app.services.frontpage_lead_service import dump_kb_file_ids, parse_kb_file_ids

    desc = str(payload.description or "").strip()
    if len(desc) < 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Description must be at least 10 characters")
    settings = get_lead_sales_settings(db)
    if not payload.rewrite and settings.system_prompt:
        refresh_lead_sales_kb(settings, db)
        return {
            "system_prompt": settings.system_prompt,
            "skipped": True,
            "kb_file_ids": parse_kb_file_ids(settings.kb_file_ids),
        }
    clean_ids = sanitize_kb_file_ids(db, payload.kb_file_ids, scope=KB_SCOPE_SALES)
    files = get_kb_files_by_ids(db, clean_ids, scope=KB_SCOPE_SALES)
    if payload.kb_file_ids and not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No sales knowledge base files found for selected IDs")
    prompt = generate_lead_sales_master_prompt(db, description=desc, knowledge_files=files)
    settings.prompt_description = desc
    settings.system_prompt = prompt
    settings.kb_file_ids = dump_kb_file_ids([f.id for f in files])
    settings.updated_at = datetime.utcnow()
    refresh_lead_sales_kb(settings, db)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return {
        "system_prompt": prompt,
        "settings": lead_sales_settings_out(settings),
        "kb_files_used": [f.original_filename for f in files],
        "prompt_chars": len(prompt),
    }


@admin_router.get("/lead-sales/tasks")
def list_lead_sales_tasks(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask

    rows = list(
        db.execute(select(LeadSalesTask).order_by(LeadSalesTask.created_at.desc()).limit(300)).scalars()
    )
    lead_codes: dict[str, str] = {}
    if rows:
        lead_ids = [row.lead_id for row in rows]
        for lead in db.execute(select(FrontpageLeadCall).where(FrontpageLeadCall.id.in_(lead_ids))).scalars():
            lead_codes[lead.id] = lead.lead_code or ""
    return {"tasks": [_sales_task_out(db, row, lead_code=lead_codes.get(row.lead_id)) for row in rows]}


@admin_router.get("/lead-sales/tasks/export")
def export_lead_sales_tasks_csv(db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from fastapi.responses import Response

    from app.models.lead_sales_task import LeadSalesTask
    from app.services.csv_export_service import lead_sales_tasks_csv
    from app.services.lead_sales_service import get_lead_sales_settings

    rows = list(
        db.execute(select(LeadSalesTask).order_by(LeadSalesTask.created_at.desc()).limit(300)).scalars()
    )
    lead_codes: dict[str, str] = {}
    if rows:
        lead_ids = [row.lead_id for row in rows]
        for lead in db.execute(select(FrontpageLeadCall).where(FrontpageLeadCall.id.in_(lead_ids))).scalars():
            lead_codes[lead.id] = lead.lead_code or ""
    settings = get_lead_sales_settings(db)
    body, filename = lead_sales_tasks_csv(rows, lead_codes=lead_codes, settings=settings)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@admin_router.get("/lead-sales/tasks/{task_id}")
def get_lead_sales_task(task_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask
    row = db.get(LeadSalesTask, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales task not found")
    lead = db.get(FrontpageLeadCall, row.lead_id)
    return {"task": _sales_task_out(db, row, lead_code=lead.lead_code if lead else None), "lead": _lead_out(lead) if lead else None}


@admin_router.post("/lead-sales/tasks/from-lead/{lead_id}")
def create_lead_sales_task_from_lead_route(lead_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.services.lead_sales_service import create_sales_task_from_lead

    try:
        task, already_exists = create_sales_task_from_lead(db, lead_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    lead = db.get(FrontpageLeadCall, lead_id)
    return {
        "task": _sales_task_out(db, task, lead_code=lead.lead_code if lead else None),
        "already_exists": already_exists,
    }


@admin_router.get("/lead-sources/{lead_id}/sales-task")
def get_lead_source_sales_task(lead_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.services.lead_sales_service import get_sales_task_for_lead

    task = get_sales_task_for_lead(db, lead_id)
    if task is None:
        return {"task": None}
    lead = db.get(FrontpageLeadCall, lead_id)
    return {"task": _sales_task_out(db, task, lead_code=lead.lead_code if lead else None)}


@admin_router.get("/lead-sales/tasks/{task_id}/recording")
def get_lead_sales_task_recording(task_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask
    from app.services.lead_sales_recording_service import resolve_sales_task_recording
    from fastapi.responses import Response

    row = db.get(LeadSalesTask, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales task not found")
    rec = resolve_sales_task_recording(db, row)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No Telnyx recording for this sales call yet.")
    fmt = str(rec.get("format") or "mp3").lower()
    media_type = "audio/wav" if fmt == "wav" else "audio/mpeg"
    audio = rec.get("audio_bytes")
    if not isinstance(audio, (bytes, bytearray)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Could not download recording")
    return Response(content=audio, media_type=media_type, headers={"Content-Disposition": f'inline; filename="sales-{task_id}.{fmt}"'})


@admin_router.post("/lead-sales/tasks/{task_id}/regenerate-prompt")
def regenerate_lead_sales_prompt_route(task_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask
    from app.services.lead_sales_service import regenerate_sales_prompt

    row = db.get(LeadSalesTask, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales task not found")
    try:
        row = regenerate_sales_prompt(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    lead = db.get(FrontpageLeadCall, row.lead_id)
    return {"task": _sales_task_out(db, row, lead_code=lead.lead_code if lead else None)}


@admin_router.post("/lead-sales/tasks/{task_id}/pause")
def pause_lead_sales_task_route(task_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask
    from app.services.lead_sales_service import pause_sales_task

    row = db.get(LeadSalesTask, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales task not found")
    row = pause_sales_task(db, row)
    lead = db.get(FrontpageLeadCall, row.lead_id)
    return {"task": _sales_task_out(db, row, lead_code=lead.lead_code if lead else None)}


@admin_router.post("/lead-sales/tasks/{task_id}/resume")
def resume_lead_sales_task_route(task_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask
    from app.services.lead_sales_service import resume_sales_task

    row = db.get(LeadSalesTask, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales task not found")
    try:
        row = resume_sales_task(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    lead = db.get(FrontpageLeadCall, row.lead_id)
    return {"task": _sales_task_out(db, row, lead_code=lead.lead_code if lead else None)}


@admin_router.post("/lead-sales/tasks/{task_id}/call-now")
def call_now_lead_sales_task_route(task_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask
    from app.services.lead_sales_service import execute_sales_outbound_call

    row = db.get(LeadSalesTask, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales task not found")
    try:
        row = execute_sales_outbound_call(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    lead = db.get(FrontpageLeadCall, row.lead_id)
    return {"task": _sales_task_out(db, row, lead_code=lead.lead_code if lead else None)}


@admin_router.post("/lead-sales/tasks/{task_id}/cancel")
def cancel_lead_sales_task_route(task_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask
    from app.services.lead_sales_service import cancel_sales_task

    row = db.get(LeadSalesTask, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales task not found")
    row = cancel_sales_task(db, row)
    lead = db.get(FrontpageLeadCall, row.lead_id)
    return {"task": _sales_task_out(db, row, lead_code=lead.lead_code if lead else None)}


class LeadSalesTaskUpdateIn(BaseModel):
    contact_name: str | None = None
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    interest_summary: str | None = None
    sales_intent: str | None = None
    scheduled_at: str | None = None
    callback_timezone: str | None = None
    callback_consent: bool | None = None


@admin_router.put("/lead-sales/tasks/{task_id}")
def update_lead_sales_task_route(
    task_id: str,
    payload: LeadSalesTaskUpdateIn,
    db: Session = Depends(get_db),
    _admin=Depends(require_platform_admin),
):
    from app.models.lead_sales_task import LeadSalesTask
    from app.services.lead_sales_service import update_sales_task

    row = db.get(LeadSalesTask, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales task not found")
    row = update_sales_task(db, row, payload.model_dump(exclude_unset=True))
    lead = db.get(FrontpageLeadCall, row.lead_id)
    return {"task": _sales_task_out(db, row, lead_code=lead.lead_code if lead else None)}


@admin_router.delete("/lead-sales/tasks/{task_id}")
def delete_lead_sales_task_route(task_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask
    from app.services.lead_sales_service import delete_sales_task

    row = db.get(LeadSalesTask, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales task not found")
    delete_sales_task(db, row)
    return {"ok": True}


@admin_router.post("/lead-sales/tasks/{task_id}/sync-outcome")
def sync_lead_sales_outcome_route(task_id: str, db: Session = Depends(get_db), _admin=Depends(require_platform_admin)):
    from app.models.lead_sales_task import LeadSalesTask
    from app.services.lead_sales_outcome_service import sync_sales_task_outcome

    row = db.get(LeadSalesTask, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales task not found")
    try:
        row = sync_sales_task_outcome(db, row)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    lead = db.get(FrontpageLeadCall, row.lead_id)
    return {"task": _sales_task_out(db, row, lead_code=lead.lead_code if lead else None)}
