"""Interview agent labels and voice preview for the dashboard picker."""

from __future__ import annotations

import base64
import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.constants.interview_agent_regions import (
    INTERVIEW_ENGLISH_ROSTER,
    INTERVIEW_REGIONS,
    region_meta_for_agent,
    voice_env_key_for_region_gender,
)
from app.core.agent_services import SERVICE_INTERVIEW
from app.models.agent import AgentDefinition
from app.services.survey_voice_agent_service import list_agents_for_service

logger = logging.getLogger(__name__)

CANONICAL_INTERVIEW_SLUGS: frozenset[str] = frozenset(
    spec.slug for spec in INTERVIEW_ENGLISH_ROSTER
) | frozenset({"interview-ar-sultan", "interview-ar-jammal"})

CANONICAL_SLUG_BY_BUCKET: dict[tuple[str, str], str] = {
    (spec.accent_region, spec.gender): spec.slug for spec in INTERVIEW_ENGLISH_ROSTER
}
CANONICAL_SLUG_BY_BUCKET[("SA", "male")] = "interview-ar-sultan"
CANONICAL_SLUG_BY_BUCKET[("EG", "male")] = "interview-ar-jammal"


def _agent_gender(agent: AgentDefinition) -> str:
    explicit = str(getattr(agent, "gender", None) or "").strip().lower()
    if explicit in {"male", "female"}:
        return explicit
    from app.services.survey_voice_agent_service import _agent_dashboard_gender

    return _agent_dashboard_gender(agent)


def _agent_bucket_key(agent: AgentDefinition) -> tuple[str, str]:
    dialect = interview_agent_dialect_meta(agent)
    region = str(getattr(agent, "accent_region", None) or dialect.get("accent_region") or "").upper()
    gender = _agent_gender(agent)
    if gender not in {"male", "female"}:
        gender = "male"
    return region, gender


def filter_canonical_interview_agents(agents: list[AgentDefinition]) -> list[AgentDefinition]:
    """Drop legacy duplicate interview agents when a canonical slug exists for the same region/gender."""
    by_bucket: dict[tuple[str, str], list[AgentDefinition]] = defaultdict(list)
    for agent in agents:
        by_bucket[_agent_bucket_key(agent)].append(agent)

    kept_ids: set[str] = set()

    def _row_key(row: AgentDefinition) -> str:
        return str(row.id or row.slug or "")

    for bucket, bucket_agents in by_bucket.items():
        canonical_slug = CANONICAL_SLUG_BY_BUCKET.get(bucket)
        if canonical_slug:
            canonical_rows = [a for a in bucket_agents if a.slug == canonical_slug]
            if canonical_rows:
                winner = canonical_rows[0]
                kept_ids.add(_row_key(winner))
                for agent in bucket_agents:
                    if _row_key(agent) != _row_key(winner):
                        logger.warning(
                            "Dropped duplicate interview agent slug=%s id=%s bucket=%s (kept %s)",
                            agent.slug,
                            agent.id,
                            bucket,
                            canonical_slug,
                        )
                continue

        sorted_agents = sorted(
            bucket_agents,
            key=lambda row: row.updated_at or datetime.min,
            reverse=True,
        )
        kept_ids.add(_row_key(sorted_agents[0]))
        for agent in sorted_agents[1:]:
            logger.warning(
                "Dropped duplicate interview agent slug=%s id=%s bucket=%s (no canonical slug)",
                agent.slug,
                agent.id,
                bucket,
            )

    return [agent for agent in agents if _row_key(agent) in kept_ids]


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
            "accent_region": "SA",
            "flag_emoji": "🇸🇦",
        }
    if any(token in blob for token in ("jammal", "jamal", "jamel", "egypt", "egyptian", "masri", "مصر")):
        return {
            "dialect_code": "EG",
            "dialect_label": "Egyptian Arabic",
            "dialect_description": "Natural Egyptian phone style — understands Gulf & Levant replies",
            "sample_phrase": "أهلاً، معاك جمال من فريق التوظيف. سامعني كويس؟",
            "accent_region": "EG",
            "flag_emoji": "🇪🇬",
        }
    from app.services.voice_agent_runtime import agent_is_arabic

    if agent_is_arabic(agent):
        return {
            "dialect_code": "AR",
            "dialect_label": "Arabic",
            "dialect_description": "Colloquial Arabic for phone interviews",
            "sample_phrase": "السلام عليكم، معك فريق التوظيف. تسمعني؟",
            "accent_region": "AR",
            "flag_emoji": "🇸🇦",
        }

    region = region_meta_for_agent(agent)
    gender = _agent_gender(agent)
    if region:
        sample = region.sample_phrase_female if gender == "female" else region.sample_phrase_male
        return {
            "dialect_code": region.code,
            "dialect_label": region.english_label,
            "dialect_description": f"Professional {region.label} phone screening style",
            "sample_phrase": sample,
            "accent_region": region.code,
            "flag_emoji": region.flag_emoji,
        }

    return {
        "dialect_code": "GB",
        "dialect_label": "British English",
        "dialect_description": "Professional UK phone screening style",
        "sample_phrase": "Hello, this is your AI interviewer calling from the hiring team. Can you hear me clearly?",
        "accent_region": "GB",
        "flag_emoji": "🇬🇧",
    }


def _elevenlabs_platform_enabled(db: Session) -> bool:
    from app.services.provider_settings import ProviderSettingsService

    try:
        _, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="elevenlabs")
        return bool(enabled)
    except Exception:
        return False


def _resolve_elevenlabs_voice_for_preview(
    db: Session,
    agent: AgentDefinition,
    *,
    runtime_cache: dict[str, dict[str, Any]] | None = None,
) -> tuple[str | None, dict[str, Any], str]:
    """Return (elevenlabs_voice_id, voice_settings, hint). voice_id is None when unavailable."""
    dialect = interview_agent_dialect_meta(agent)
    region = str(getattr(agent, "accent_region", None) or dialect.get("accent_region") or "").upper()
    gender = _agent_gender(agent)
    env_key = voice_env_key_for_region_gender(region, gender)
    env_voice = os.environ.get(env_key, "").strip()
    if env_voice:
        from app.services.telnyx_assistant_service import parse_telnyx_assistant_voice

        _, voice_id, extras = parse_telnyx_assistant_voice(env_voice)
        if voice_id:
            settings = dict(extras)
            settings.setdefault("model_id", "eleven_multilingual_v2")
            return voice_id, settings, ""

    assistant_id = str(agent.telnyx_assistant_id or "").strip()
    if not assistant_id:
        return None, {}, "No Telnyx assistant — run provisioning or set voice env"

    cache = runtime_cache if runtime_cache is not None else {}
    if assistant_id not in cache:
        try:
            from app.services.telnyx_assistant_service import resolve_telnyx_assistant_runtime

            cache[assistant_id] = resolve_telnyx_assistant_runtime(db, assistant_id)
        except Exception as exc:
            cache[assistant_id] = {"error": str(exc)}
    runtime = cache[assistant_id]
    if runtime.get("error"):
        return None, {}, f"Telnyx error: {runtime['error']}"

    if str(runtime.get("tts_provider") or "").lower() != "elevenlabs":
        return None, {}, "Configure an ElevenLabs voice on this Telnyx assistant"

    voice_id = str(runtime.get("elevenlabs_voice_id") or "").strip()
    if not voice_id:
        return None, {}, "ElevenLabs voice ID not found on this Telnyx assistant"

    settings = dict(runtime.get("elevenlabs_voice_settings") or {})
    settings.setdefault("model_id", "eleven_multilingual_v2")
    return voice_id, settings, ""


def voice_preview_status(
    db: Session,
    agent: AgentDefinition,
    *,
    runtime_cache: dict[str, dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    """Fast list-time check — no Telnyx HTTP (preview endpoint resolves voice live)."""
    del runtime_cache
    if not _elevenlabs_platform_enabled(db):
        return False, "ElevenLabs not configured in Admin → Integrations"

    dialect = interview_agent_dialect_meta(agent)
    region = str(getattr(agent, "accent_region", None) or dialect.get("accent_region") or "").upper()
    gender = _agent_gender(agent)
    env_key = voice_env_key_for_region_gender(region, gender)
    if os.environ.get(env_key, "").strip():
        return True, ""

    if str(agent.telnyx_assistant_id or "").strip():
        return True, ""

    return False, "No Telnyx assistant — run provisioning or set voice env"


def dashboard_agent_row(
    agent: AgentDefinition,
    *,
    assigned_id: str | None,
    default_field: str,
    zone: str,
    org_country: str | None = None,
    db: Session | None = None,
    runtime_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.services.survey_voice_agent_service import (
        _agent_dashboard_language,
        _agent_region_match,
        _agent_zone_match,
    )

    dialect = interview_agent_dialect_meta(agent)
    gender = _agent_gender(agent)
    accent = str(getattr(agent, "accent_region", None) or dialect.get("accent_region") or "").upper()
    region_label = INTERVIEW_REGIONS.get(accent, INTERVIEW_REGIONS["GB"]).label if accent in INTERVIEW_REGIONS else dialect.get("dialect_label", "")

    preview_available = False
    preview_hint = "Voice preview unavailable"
    if db is not None:
        preview_available, preview_hint = voice_preview_status(db, agent, runtime_cache=runtime_cache)

    return {
        "id": agent.id,
        "name": agent.name,
        "voice_label": agent.voice_label or agent.name,
        "voice_type_label": agent.voice_type_label,
        "language": _agent_dashboard_language(agent),
        "gender": gender,
        "accent_region": accent or None,
        "region_label": region_label,
        "flag_emoji": dialect.get("flag_emoji"),
        "is_default_for_org": bool(assigned_id and assigned_id == agent.id),
        "is_platform_default": bool(getattr(agent, default_field, False)),
        "is_zone_match": _agent_zone_match(agent, zone) or _agent_region_match(agent, org_country),
        "market_zone": zone,
        "voice_preview_available": preview_available,
        "voice_preview_hint": preview_hint,
        **{k: v for k, v in dialect.items() if k not in {"accent_region", "flag_emoji"}},
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
        logger.warning("interview_voice_preview org=%s agent=%s result=not_found", org_id, agent_id)
        raise ValueError("Interview agent not found")

    dialect = interview_agent_dialect_meta(agent)
    sample_text = dialect["sample_phrase"]
    assistant_id = str(agent.telnyx_assistant_id or "").strip()

    voice_id, voice_settings, hint = _resolve_elevenlabs_voice_for_preview(db, agent)
    if not voice_id:
        logger.warning(
            "interview_voice_preview org=%s agent=%s slug=%s telnyx=%s result=unavailable hint=%s",
            org_id,
            agent_id,
            agent.slug,
            assistant_id or "(unset)",
            hint,
        )
        raise ValueError(hint or "Voice preview unavailable")

    from app.services.providers.elevenlabs_service import ElevenLabsProviderService

    result = ElevenLabsProviderService.synthesize_text_result(
        db,
        text=sample_text,
        voice_id=voice_id,
        voice_settings=voice_settings,
    )
    if not result.get("ok"):
        err = str(result.get("error") or "TTS failed")
        logger.warning(
            "interview_voice_preview org=%s agent=%s slug=%s telnyx=%s voice=%s result=tts_failed error=%s",
            org_id,
            agent_id,
            agent.slug,
            assistant_id or "(unset)",
            voice_id,
            err,
        )
        raise ValueError(f"Could not generate voice sample: {err}")

    audio = bytes(result.get("audio_data") or b"")
    logger.info(
        "interview_voice_preview org=%s agent=%s slug=%s telnyx=%s voice=%s bytes=%d result=ok",
        org_id,
        agent_id,
        agent.slug,
        assistant_id or "(unset)",
        voice_id,
        len(audio),
    )
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
