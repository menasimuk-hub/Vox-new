"""Voice note download and transcription for Abuu WhatsApp."""

from __future__ import annotations

import logging
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.providers.deepinfra_service import DeepInfraProviderService
from app.services.survey_wa_voice_note_media_service import download_media_file, extract_media_items

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.45
MIN_TRANSCRIPT_CHARS = 2
DEFAULT_STT_LANGUAGE = "ar"

_LAUGHTER_PATTERN = re.compile(
    r"^(?:ha+|he+|hi+|ho+|hu+|ah+|eh+|oh+|uh+|lol+|haha+|hehe+|hihi+|"
    r"هه+|ح+$|ه+$|م+$|😂+|🤣+)+$",
    re.IGNORECASE,
)
_REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{4,}")


def _stt_language(language: str | None) -> str:
    raw = str(language or DEFAULT_STT_LANGUAGE).strip().lower()
    if raw.startswith("ar"):
        return "ar"
    if raw.startswith("en"):
        return "en"
    return DEFAULT_STT_LANGUAGE


def is_low_quality_transcript(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return True
    if len(cleaned) < MIN_TRANSCRIPT_CHARS:
        return True
    if _LAUGHTER_PATTERN.match(cleaned):
        return True
    if _REPEATED_CHAR_PATTERN.search(cleaned) and len(cleaned.split()) <= 2:
        return True
    alpha = re.sub(r"[\W_]+", "", cleaned, flags=re.UNICODE)
    if alpha and len(set(alpha.lower())) <= 2 and len(alpha) >= 4:
        return True
    return False


@dataclass(frozen=True)
class AbuuVoiceTranscription:
    ok: bool
    transcript: str
    confidence: float
    media_url: str | None = None
    content_type: str | None = None
    storage_path: str | None = None
    error: str | None = None


def _estimate_confidence(text: str) -> float:
    cleaned = str(text or "").strip()
    if not cleaned:
        return 0.0
    if is_low_quality_transcript(cleaned):
        return 0.1
    if len(cleaned) < MIN_TRANSCRIPT_CHARS:
        return 0.2
    if len(cleaned.split()) >= 2:
        return 0.9
    return 0.75


def _storage_root() -> Path:
    settings = get_settings()
    raw = str(getattr(settings, "abuu_voice_note_dir", "") or "data/abuu_voice_notes").strip()
    root = Path(raw)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root


class AbuuVoiceService:
    @staticmethod
    def transcribe_inbound(
        main_db: Session,
        *,
        record: dict[str, Any],
        customer_phone: str,
        language: str | None = None,
    ) -> AbuuVoiceTranscription:
        media_items = extract_media_items(record)
        if not media_items:
            return AbuuVoiceTranscription(ok=False, transcript="", confidence=0.0, error="no_media")

        media = media_items[0]
        media_url = str(media.get("url") or "").strip()
        content_type = str(media.get("content_type") or "audio/ogg").strip()
        if not media_url:
            return AbuuVoiceTranscription(ok=False, transcript="", confidence=0.0, error="missing_media_url")

        job_id = str(uuid.uuid4())
        dest = _storage_root() / customer_phone.replace("+", "") / f"{job_id}.ogg"
        try:
            path, _size, resolved_type = download_media_file(
                main_db,
                media_url=media_url,
                content_type=content_type,
                original_filename=str(media.get("original_filename") or "voice.ogg"),
                dest_path=dest,
                max_bytes=16 * 1024 * 1024,
                timeout_seconds=30,
            )
            transcript = AbuuVoiceService._transcribe_file(
                main_db,
                path,
                language=_stt_language(language),
            )
            confidence = _estimate_confidence(transcript)
            cleaned = transcript.strip()
            ok = bool(cleaned) and not is_low_quality_transcript(cleaned)
            return AbuuVoiceTranscription(
                ok=ok,
                transcript=cleaned,
                confidence=confidence,
                media_url=media_url,
                content_type=resolved_type or content_type,
                storage_path=str(path),
                error=None if ok else "low_confidence_or_empty",
            )
        except Exception as exc:
            logger.warning("abuu_voice_transcription_failed phone=%s err=%s", customer_phone, exc, exc_info=True)
            return AbuuVoiceTranscription(
                ok=False,
                transcript="",
                confidence=0.0,
                media_url=media_url,
                content_type=content_type,
                error=str(exc),
            )

    @staticmethod
    def _transcribe_deepinfra(main_db: Session, audio_path: Path, *, language: str | None) -> str:
        stt_lang = _stt_language(language)
        result = DeepInfraProviderService.transcribe_audio_file(
            main_db,
            audio_path=audio_path,
            language=stt_lang,
        )
        return str(result.get("text") or "").strip()

    @staticmethod
    def _transcribe_whisper_cpp(audio_path: Path) -> str:
        from app.services.survey_wa_whisper_service import transcribe_with_whisper_cpp

        result = transcribe_with_whisper_cpp(audio_path)
        return str(result.get("text") or "").strip()

    @staticmethod
    def _transcribe_groq(main_db: Session, audio_path: Path, *, language: str | None) -> str:
        stt_lang = _stt_language(language)
        with tempfile.NamedTemporaryFile(suffix=audio_path.suffix, delete=False) as tmp:
            tmp.write(audio_path.read_bytes())
            tmp_path = Path(tmp.name)
        try:
            from app.services.providers.groq_service import GroqProviderService

            payload = GroqProviderService.transcribe_audio_result(
                main_db,
                audio=tmp_path.read_bytes(),
                filename=tmp_path.name,
                content_type="audio/ogg",
                language=stt_lang,
            )
            return str(payload.get("text") or "").strip()
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _transcribe_file(main_db: Session, audio_path: Path, *, language: str | None) -> str:
        from app.abuu.voice_interpretation.stt_config import stt_provider_order

        providers = stt_provider_order()
        for provider in providers:
            try:
                if provider == "deepinfra" and DeepInfraProviderService.is_configured(main_db):
                    text = AbuuVoiceService._transcribe_deepinfra(main_db, audio_path, language=language)
                    if text:
                        return text
                elif provider == "whisper_cpp":
                    text = AbuuVoiceService._transcribe_whisper_cpp(audio_path)
                    if text:
                        return text
                elif provider == "groq":
                    text = AbuuVoiceService._transcribe_groq(main_db, audio_path, language=language)
                    if text:
                        return text
            except Exception:
                logger.warning("abuu_stt_provider_failed provider=%s", provider, exc_info=True)
        return ""
