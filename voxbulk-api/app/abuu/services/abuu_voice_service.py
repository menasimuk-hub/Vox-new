"""Voice note download and transcription for Abuu WhatsApp."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.voice_interpretation.stt_dialect_correction import (
    STT_DIALECT_PROMPT,
    correct_stt_transcript,
    is_stt_garbage,
    rescore_after_correction,
)
from app.core.config import get_settings
from app.services.providers.deepgram_service import DeepgramProviderService
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


def _dialect_prompt_for_language(language: str | None) -> str | None:
    if _stt_language(language) == "ar":
        return STT_DIALECT_PROMPT
    return None


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
    raw_transcript: str = ""
    corrected_transcript: str = ""
    needs_clarification: bool = False
    clarification_reason: str | None = None
    correction_applied: bool = False
    garbage_detected: bool = False
    file_size_bytes: int | None = None
    duration_seconds: float | None = None


def _duration_from_record(record: dict[str, Any] | None) -> float | None:
    if not record:
        return None
    for key in ("duration", "duration_seconds", "voice_duration", "audio_duration"):
        raw = record.get(key)
        if raw is not None:
            try:
                val = float(raw)
                if val > 1000:
                    return val / 1000.0
                return val
            except (TypeError, ValueError):
                continue
    whatsapp = record.get("whatsapp_message")
    if isinstance(whatsapp, dict):
        for key in ("duration", "voice", "audio"):
            nested = whatsapp.get(key)
            if isinstance(nested, dict) and nested.get("duration") is not None:
                try:
                    val = float(nested.get("duration"))
                    return val / 1000.0 if val > 1000 else val
                except (TypeError, ValueError):
                    pass
    return None


def _duration_from_file(audio_path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


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


def _audio_content_type(audio_path: Path) -> str:
    suffix = audio_path.suffix.lower()
    if suffix in {".ogg", ".oga"}:
        return "audio/ogg"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix in {".m4a", ".mp4"}:
        return "audio/mp4"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".webm":
        return "audio/webm"
    return "application/octet-stream"


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

        stt_lang = _stt_language(language)
        job_id = str(uuid.uuid4())
        dest = _storage_root() / customer_phone.replace("+", "") / f"{job_id}.ogg"
        try:
            path: Path | None = None
            file_size = 0
            resolved_type = content_type
            last_dl_error: Exception | None = None
            for dl_attempt in range(1, 5):
                try:
                    path, file_size, resolved_type = download_media_file(
                        main_db,
                        media_url=media_url,
                        content_type=content_type,
                        original_filename=str(media.get("original_filename") or "voice.ogg"),
                        dest_path=dest,
                        max_bytes=16 * 1024 * 1024,
                        timeout_seconds=30,
                    )
                    if file_size < 128:
                        raise ValueError("downloaded_audio_too_small")
                    break
                except Exception as exc:
                    last_dl_error = exc
                    logger.warning(
                        "abuu_voice_download_retry phone=%s attempt=%s err=%s",
                        customer_phone,
                        dl_attempt,
                        exc,
                    )
                    if dest.exists():
                        try:
                            dest.unlink()
                        except OSError:
                            pass
                    if dl_attempt < 4:
                        time.sleep(0.5 * (2 ** (dl_attempt - 1)))
            if path is None:
                raise ValueError(str(last_dl_error) if last_dl_error else "Media download failed")
            duration_seconds = _duration_from_record(record) or _duration_from_file(path)
            raw_transcript = AbuuVoiceService._transcribe_file(
                main_db,
                path,
                language=stt_lang,
                dialect_prompt=_dialect_prompt_for_language(language),
            ).strip()
            raw_confidence = _estimate_confidence(raw_transcript)

            logger.info(
                "abuu_stt_raw | phone=%s transcript=%r confidence=%.2f",
                customer_phone,
                raw_transcript,
                raw_confidence,
            )

            is_garbage = is_stt_garbage(raw_transcript, language=stt_lang)
            needs_clarification = False
            clarification_reason: str | None = None
            correction_failed = False

            if is_garbage:
                corrected_transcript = raw_transcript
                confidence = 0.2
                needs_clarification = True
                clarification_reason = "low_quality_audio"
                logger.warning(
                    "abuu_stt_garbage | phone=%s raw=%r reason='garbage_check_failed'",
                    customer_phone,
                    raw_transcript,
                )
            else:
                corrected_transcript, correction_failed = correct_stt_transcript(
                    main_db,
                    raw=raw_transcript,
                    phone=customer_phone,
                    language=stt_lang,
                )
                confidence = rescore_after_correction(
                    raw=raw_transcript,
                    corrected=corrected_transcript,
                    raw_confidence=raw_confidence,
                    correction_failed=correction_failed,
                )
                if correction_failed or is_low_quality_transcript(corrected_transcript):
                    needs_clarification = True
                    clarification_reason = "low_quality_audio"

            logger.info(
                "abuu_stt_correction | phone=%s raw=%r corrected=%r confidence=%.2f",
                customer_phone,
                raw_transcript,
                corrected_transcript,
                confidence,
            )

            ok = bool(corrected_transcript) and not is_low_quality_transcript(corrected_transcript)
            if needs_clarification and confidence <= 0.2:
                ok = False

            return AbuuVoiceTranscription(
                ok=ok,
                transcript=corrected_transcript,
                confidence=confidence,
                media_url=media_url,
                content_type=resolved_type or content_type,
                storage_path=str(path),
                error=None if ok else "low_confidence_or_empty",
                raw_transcript=raw_transcript,
                corrected_transcript=corrected_transcript,
                needs_clarification=needs_clarification,
                clarification_reason=clarification_reason,
                correction_applied=(corrected_transcript != raw_transcript),
                garbage_detected=is_garbage,
                file_size_bytes=file_size,
                duration_seconds=duration_seconds,
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
    def _transcribe_deepgram(
        main_db: Session,
        audio_path: Path,
        *,
        language: str | None,
        dialect_prompt: str | None = None,
    ) -> str:
        stt_lang = _stt_language(language)
        payload = DeepgramProviderService.transcribe_audio_result(
            main_db,
            audio=audio_path.read_bytes(),
            filename=audio_path.name,
            content_type=_audio_content_type(audio_path),
            language=stt_lang,
        )
        if not payload.get("ok", True) and not payload.get("text"):
            err = payload.get("error") or payload.get("status_code")
            raise RuntimeError(f"Deepgram STT failed: {err}")
        return str(payload.get("text") or "").strip()

    @staticmethod
    def _transcribe_deepinfra(
        main_db: Session,
        audio_path: Path,
        *,
        language: str | None,
        dialect_prompt: str | None = None,
    ) -> str:
        stt_lang = _stt_language(language)
        result = DeepInfraProviderService.transcribe_audio_file(
            main_db,
            audio_path=audio_path,
            language=stt_lang,
            prompt=dialect_prompt,
        )
        return str(result.get("text") or "").strip()

    @staticmethod
    def _transcribe_whisper_cpp(
        audio_path: Path,
        *,
        language: str | None,
        dialect_prompt: str | None = None,
    ) -> str:
        from app.services.survey_wa_whisper_service import transcribe_with_whisper_cpp

        whisper_lang = _stt_language(language) if _stt_language(language) in {"ar", "en"} else "auto"
        result = transcribe_with_whisper_cpp(
            audio_path,
            language=whisper_lang,
            initial_prompt=dialect_prompt,
        )
        return str(result.get("text") or "").strip()

    @staticmethod
    def _transcribe_groq(
        main_db: Session,
        audio_path: Path,
        *,
        language: str | None,
        dialect_prompt: str | None = None,
    ) -> str:
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
                prompt=dialect_prompt,
            )
            if not payload.get("ok", True) and not payload.get("text"):
                return ""
            return str(payload.get("text") or "").strip()
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _transcribe_file(
        main_db: Session,
        audio_path: Path,
        *,
        language: str | None,
        dialect_prompt: str | None = None,
    ) -> str:
        from app.abuu.voice_interpretation.stt_config import stt_provider_order

        providers = stt_provider_order()
        deepgram_ready = DeepgramProviderService.is_configured(main_db)
        deepinfra_ready = DeepInfraProviderService.is_configured(main_db)
        failures: list[str] = []
        for provider in providers:
            try:
                if provider == "deepgram":
                    if not deepgram_ready:
                        failures.append("deepgram:not_configured")
                        continue
                    text = AbuuVoiceService._transcribe_deepgram(
                        main_db,
                        audio_path,
                        language=language,
                        dialect_prompt=dialect_prompt,
                    )
                    if text:
                        logger.info("abuu_stt_ok provider=deepgram chars=%s", len(text))
                        return text
                    failures.append("deepgram:empty")
                elif provider == "deepinfra":
                    if not deepinfra_ready:
                        failures.append("deepinfra:not_configured")
                        continue
                    text = AbuuVoiceService._transcribe_deepinfra(
                        main_db,
                        audio_path,
                        language=language,
                        dialect_prompt=dialect_prompt,
                    )
                    if text:
                        logger.info("abuu_stt_ok provider=deepinfra chars=%s", len(text))
                        return text
                    failures.append("deepinfra:empty")
                elif provider == "whisper_cpp":
                    text = AbuuVoiceService._transcribe_whisper_cpp(
                        audio_path,
                        language=language,
                        dialect_prompt=dialect_prompt,
                    )
                    if text:
                        logger.info("abuu_stt_ok provider=whisper_cpp chars=%s", len(text))
                        return text
                    failures.append("whisper_cpp:empty")
                elif provider == "groq":
                    text = AbuuVoiceService._transcribe_groq(
                        main_db,
                        audio_path,
                        language=language,
                        dialect_prompt=dialect_prompt,
                    )
                    if text:
                        logger.info("abuu_stt_ok provider=groq chars=%s", len(text))
                        return text
                    failures.append("groq:empty")
                else:
                    failures.append(f"{provider}:unknown")
            except Exception as exc:
                failures.append(f"{provider}:{type(exc).__name__}")
                logger.warning("abuu_stt_provider_failed provider=%s", provider, exc_info=True)
        logger.warning(
            "abuu_stt_all_providers_failed path=%s providers=%s deepgram=%s deepinfra=%s failures=%s",
            audio_path,
            ",".join(providers),
            deepgram_ready,
            deepinfra_ready,
            ",".join(failures) or "none",
        )
        return ""
