"""Voice note adapter for Abuu agent."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.agent import AbuuAgentLoop
from app.abuu.services.abuu_voice_service import AbuuVoiceService
from app.abuu.services.reply_service import voice_low_confidence_message, voice_unclear_transcript_message, voice_fallback_message
from app.abuu.services.abuu_voice_service import is_low_quality_transcript

logger = logging.getLogger(__name__)


def transcribe_and_run_agent(
    abuu_db: Session,
    main_db: Session,
    *,
    phone: str,
    record: dict[str, Any],
    lang: str,
    message_id: str | None = None,
    org_id: str | None = None,
    has_active_order: bool = False,
) -> dict[str, Any]:
    voice = AbuuVoiceService.transcribe_inbound(
        main_db,
        record=record,
        customer_phone=phone,
        language=lang,
    )
    if not voice.ok or not (voice.transcript or "").strip():
        return {
            "handled": True,
            "action": "voice_failed",
            "reply": voice_low_confidence_message(lang)
            if voice.confidence is not None and voice.confidence < 0.45
            else voice_fallback_message(lang, active_order=has_active_order),
        }
    if is_low_quality_transcript(voice.transcript):
        return {
            "handled": True,
            "action": "voice_failed",
            "reply": voice_unclear_transcript_message(lang),
        }
    return AbuuAgentLoop.run(
        abuu_db,
        main_db,
        phone=phone,
        text=voice.transcript.strip(),
        message_id=message_id,
        org_id=org_id,
        input_source="voice",
    )
