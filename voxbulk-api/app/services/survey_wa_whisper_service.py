"""Local whisper.cpp transcription for survey voice notes."""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path

from app.services.survey_wa_voice_note_settings import voice_note_settings

logger = logging.getLogger(__name__)
LOG_PREFIX = "[survey-wa-whisper]"


class WhisperTranscriptionError(RuntimeError):
    pass


def normalize_audio_for_whisper(source_path: Path, *, ffmpeg_binary: str, timeout_seconds: int) -> Path:
    out_dir = source_path.parent
    wav_path = out_dir / f"{source_path.stem}.whisper.wav"
    cmd = [
        ffmpeg_binary,
        "-y",
        "-i",
        str(source_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    logger.info("%s ffmpeg_normalize input=%s output=%s", LOG_PREFIX, source_path, wav_path)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(10, int(timeout_seconds)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise WhisperTranscriptionError("Audio normalization timed out") from exc
    if proc.returncode != 0 or not wav_path.exists():
        stderr = (proc.stderr or proc.stdout or "").strip()
        raise WhisperTranscriptionError(f"ffmpeg failed: {stderr[:500]}")
    return wav_path


def _parse_whisper_output(stdout: str, stderr: str, txt_path: Path | None) -> tuple[str, str | None]:
    text = ""
    if txt_path and txt_path.exists():
        text = txt_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        combined = f"{stdout}\n{stderr}"
        for line in combined.splitlines():
            if line.strip().startswith("[") and "]" in line:
                continue
            candidate = line.strip()
            if candidate and not candidate.lower().startswith("whisper"):
                text = candidate if not text else f"{text} {candidate}"
    text = re.sub(r"\s+", " ", text).strip()
    detected_language = None
    lang_match = re.search(r"detected language:\s*([a-zA-Z_-]+)", f"{stdout}\n{stderr}", re.I)
    if lang_match:
        detected_language = lang_match.group(1).strip().lower()
    lang_match2 = re.search(r"language\s*=\s*'?([a-zA-Z_-]+)'?", f"{stdout}\n{stderr}", re.I)
    if not detected_language and lang_match2:
        detected_language = lang_match2.group(1).strip().lower()
    return text, detected_language


def transcribe_with_whisper_cpp(
    audio_path: Path,
    *,
    language: str | None = None,
    initial_prompt: str | None = None,
) -> dict:
    cfg = voice_note_settings()
    binary = cfg["whisper_cpp_binary"]
    model = cfg["whisper_cpp_model"]
    if not model:
        raise WhisperTranscriptionError("WHISPER_CPP_MODEL is not configured")
    if not Path(model).exists():
        raise WhisperTranscriptionError(f"Whisper model not found: {model}")

    ffmpeg = cfg["ffmpeg_binary"]
    timeout_seconds = int(cfg["voice_note_transcription_timeout_seconds"] or 180)
    wav_path = normalize_audio_for_whisper(audio_path, ffmpeg_binary=ffmpeg, timeout_seconds=timeout_seconds)

    whisper_lang = str(language or "auto").strip().lower() or "auto"
    if whisper_lang not in {"auto", "ar", "en"}:
        whisper_lang = "auto"

    with tempfile.TemporaryDirectory(prefix="whisper-out-") as tmp:
        out_base = str(Path(tmp) / "transcript")
        out_txt = Path(f"{out_base}.txt")
        started = time.perf_counter()

        def _build_cmd(*, use_prompt: bool) -> list[str]:
            cmd_a = [
                binary,
                "-m",
                model,
                "-f",
                str(wav_path),
                "-l",
                whisper_lang,
                "-otxt",
                "-of",
                out_base,
            ]
            cmd_b = [
                binary,
                "-m",
                model,
                "-f",
                str(wav_path),
                "-l",
                whisper_lang,
                "--output-txt",
                "--output-file",
                out_base,
            ]
            if use_prompt and initial_prompt:
                cmd_a.extend(["--prompt", str(initial_prompt).strip()])
                cmd_b.extend(["--prompt", str(initial_prompt).strip()])
            return [cmd_a, cmd_b]

        commands = _build_cmd(use_prompt=True)
        prompt_fallback = bool(initial_prompt)
        last_error = ""
        stdout = stderr = ""
        for cmd in commands:
            logger.info("%s whisper_started cmd=%s", LOG_PREFIX, " ".join(cmd))
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=max(30, timeout_seconds),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise WhisperTranscriptionError("Whisper transcription timed out") from exc
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            if proc.returncode == 0:
                text, language = _parse_whisper_output(stdout, stderr, out_txt if out_txt.exists() else None)
                if text:
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    logger.info(
                        "%s whisper_completed language=%s duration_ms=%s chars=%s",
                        LOG_PREFIX,
                        language,
                        elapsed_ms,
                        len(text),
                    )
                    return {
                        "text": text,
                        "detected_language": language,
                        "transcription_model": Path(model).name,
                        "transcription_duration_ms": elapsed_ms,
                    }
            last_error = (stderr or stdout or f"exit {proc.returncode}").strip()
        if prompt_fallback:
            logger.warning("%s whisper_prompt_unsupported retrying_without_prompt", LOG_PREFIX)
            commands = _build_cmd(use_prompt=False)
            for cmd in commands:
                logger.info("%s whisper_started cmd=%s", LOG_PREFIX, " ".join(cmd))
                try:
                    proc = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=max(30, timeout_seconds),
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise WhisperTranscriptionError("Whisper transcription timed out") from exc
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
                if proc.returncode == 0:
                    text, language = _parse_whisper_output(stdout, stderr, out_txt if out_txt.exists() else None)
                    if text:
                        elapsed_ms = int((time.perf_counter() - started) * 1000)
                        logger.info(
                            "%s whisper_completed language=%s duration_ms=%s chars=%s",
                            LOG_PREFIX,
                            language,
                            elapsed_ms,
                            len(text),
                        )
                        return {
                            "text": text,
                            "detected_language": language,
                            "transcription_model": Path(model).name,
                            "transcription_duration_ms": elapsed_ms,
                        }
                last_error = (stderr or stdout or f"exit {proc.returncode}").strip()
        raise WhisperTranscriptionError(last_error[:500] or "Whisper produced empty transcript")
