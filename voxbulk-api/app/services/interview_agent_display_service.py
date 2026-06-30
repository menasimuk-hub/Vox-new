"""Interview agent labels and voice preview for the dashboard picker."""

from __future__ import annotations

import base64
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent import AgentDefinition
from app.services.survey_voice_agent_service import list_agents_for_service
from app.core.agent_services import SERVICE_INTERVIEW


def interview_agent_dialect_meta(agent: AgentDefinition) -> dict[str, str]:
    """Human-facing dialect badge + sample line for the interview agent picker."""
    blob = " ".join(
        str(getattr(agent, attr, "") or "")
        for attr in ("slug", "name", "voice_label", "voice_type_label", "description")
    ).lower()

    if "sultan" in blob or "saudi" in blob or "gulf" in blob or "khaleeji" in blob or "interview-ar-sultan" in blob:
        return {
            "dialect_code": "SA",
            "dialect_label": "Saudi Gulf",
            "dialect_description": "Colloquial Khaleeji phone style — natural, not formal Arabic",
            "sample_phrase": "السلام عليكم، معك سلطان من فريق التوظيف. تسمعني زين؟",
        }
    if any(token in blob for token in ("jammal", "jamal", "jamel", "egypt", "egyptian", "masri", "مصر")):
        return {
            "dialect_code": "EG",
            "dialect_label": "Egyptian Arabic",
            "dialect_description": "Natural Egyptian phone style — understands Gulf & Levant replies",
            "sample_phrase": "أهلاً، معاك جمال من فريق التوظيف. سامعني كويس؟",
        }
    from app.services.voice_agent_runtime import agent_is_arabic

    if agent_is_arabic(agent):
        return {
            "dialect_code": "AR",
            "dialect_label": "Arabic",
            "dialect_description": "Colloquial Arabic for phone interviews",
            "sample_phrase": "السلام عليكم، معك فريق التوظيف. تسمعني؟",
        }
    return {
        "dialect_code": "GB",
        "dialect_label": "British English",
        "dialect_description": "Professional UK phone screening style",
        "sample_phrase": "Hello, this is your AI interviewer calling from the hiring team. Can you hear me clearly?",
    }


def dashboard_agent_row(agent: AgentDefinition, *, assigned_id: str | None, default_field: str, zone: str) -> dict[str, Any]:
    from app.services.survey_voice_agent_service import (
        _agent_dashboard_gender,
        _agent_dashboard_language,
        _agent_zone_match,
    )

    dialect = interview_agent_dialect_meta(agent)
    return {
        "id": agent.id,
        "name": agent.name,
        "voice_label": agent.voice_label or agent.name,
        "voice_type_label": agent.voice_type_label,
        "language": _agent_dashboard_language(agent),
        "gender": _agent_dashboard_gender(agent),
        "is_default_for_org": bool(assigned_id and assigned_id == agent.id),
        "is_platform_default": bool(getattr(agent, default_field, False)),
        "is_zone_match": _agent_zone_match(agent, zone),
        "market_zone": zone,
        **dialect,
    }


def get_interview_agent_for_org(db: Session, *, agent_id: str, org_id: str) -> AgentDefinition | None:
    allowed = {a.id for a in list_agents_for_service(db, service_key=SERVICE_INTERVIEW, org_id=org_id)}
    if agent_id not in allowed:
        return None
    agent = db.get(AgentDefinition, agent_id)
    if agent is None or not agent.is_active or not agent.supports_interview:
        return None
    return agent


def preview_interview_agent_voice(db: Session, *, agent_id: str, org_id: str) -> dict[str, Any]:
    """Synthesize a short TTS sample using the agent's Telnyx/ElevenLabs voice."""
    agent = get_interview_agent_for_org(db, agent_id=agent_id, org_id=org_id)
    if agent is None:
        raise ValueError("Interview agent not found")

    assistant_id = str(agent.telnyx_assistant_id or "").strip()
    if not assistant_id:
        raise ValueError("This agent has no Telnyx assistant configured")

    from app.services.telnyx_assistant_service import resolve_telnyx_assistant_runtime

    runtime = resolve_telnyx_assistant_runtime(db, assistant_id)
    dialect = interview_agent_dialect_meta(agent)
    sample_text = dialect["sample_phrase"]

    if str(runtime.get("tts_provider") or "").lower() != "elevenlabs":
        raise ValueError(
            "Voice preview works with ElevenLabs voices (Sultan, etc.). "
            "Azure-only agents: use Admin → Agents → Test call."
        )

    voice_id = str(runtime.get("elevenlabs_voice_id") or "").strip()
    if not voice_id:
        raise ValueError("ElevenLabs voice ID not found on this Telnyx assistant")

    from app.services.providers.elevenlabs_service import ElevenLabsProviderService

    voice_settings = dict(runtime.get("elevenlabs_voice_settings") or {})
    voice_settings.setdefault("model_id", "eleven_multilingual_v2")
    result = ElevenLabsProviderService.synthesize_text_result(
        db,
        text=sample_text,
        voice_id=voice_id,
        voice_settings=voice_settings,
    )
    if not result.get("ok"):
        raise ValueError(f"Could not generate voice sample: {result.get('error') or 'TTS failed'}")

    audio = bytes(result.get("audio_data") or b"")
    return {
        "agent_id": agent.id,
        "voice_label": agent.voice_label or agent.name,
        "dialect_code": dialect["dialect_code"],
        "dialect_label": dialect["dialect_label"],
        "sample_text": sample_text,
        "content_type": str(result.get("audio_mime") or "audio/mpeg"),
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "billing_note": "Short preview only — no charge to your wallet (uses platform TTS quota).",
    }
