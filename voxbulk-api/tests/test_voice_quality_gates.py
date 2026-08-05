"""Voice STT quality gates — silence rejection before STT and hallucination flagging after."""

from pathlib import Path

import pytest

from app.services import voice_transcription_service as vts
from app.services.voice_transcription_service import (
    MIN_SPEECH_SECONDS,
    looks_like_hallucination,
    no_speech_reason,
)


@pytest.mark.parametrize(
    "text",
    [
        "Her şey yolunda mı?",
        "her sey yolunda mi",
        "Vallahi en enteresan, bizimkiler sürer.",
        "Altyazı M.K.",
        "Abone olmayı unutmayın!",
        "Thanks for watching!",
        "Subtitles by the Amara.org community",
    ],
)
def test_known_whisper_artifacts_are_flagged(text):
    assert looks_like_hallucination(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "We are looking at packaging machines for next quarter.",
        "نبحث عن خطوط تعبئة جديدة",
        "Her şeyden önce fiyat listesi istiyorum",
        "Thank you, that was helpful",
    ],
)
def test_real_answers_are_not_flagged(text):
    assert looks_like_hallucination(text) is False


def test_clip_shorter_than_the_minimum_is_rejected_before_stt(monkeypatch, tmp_path):
    monkeypatch.setattr(vts, "_mean_volume_db", lambda _p: -12.0)
    clip = tmp_path / "clip.ogg"
    clip.write_bytes(b"x")

    assert no_speech_reason(clip, MIN_SPEECH_SECONDS - 0.1) == "audio_too_short"


def test_silent_clip_is_rejected_before_stt(monkeypatch, tmp_path):
    monkeypatch.setattr(vts, "_mean_volume_db", lambda _p: -91.0)
    clip = tmp_path / "clip.ogg"
    clip.write_bytes(b"x")

    assert no_speech_reason(clip, 4.0) == "audio_silent"


def test_audible_clip_passes_the_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(vts, "_mean_volume_db", lambda _p: -21.0)
    clip = tmp_path / "clip.ogg"
    clip.write_bytes(b"x")

    assert no_speech_reason(clip, 4.0) is None


def test_gate_stays_open_when_loudness_cannot_be_measured(monkeypatch, tmp_path):
    """No ffmpeg means no volume reading — never drop a recording we cannot inspect."""
    monkeypatch.setattr(vts, "_mean_volume_db", lambda _p: None)
    clip = tmp_path / "clip.ogg"
    clip.write_bytes(b"x")

    assert no_speech_reason(clip, None) is None


def test_mean_volume_parses_ffmpeg_output(monkeypatch, tmp_path):
    class _Proc:
        stderr = b"[Parsed_volumedetect_0 @ 0x1] mean_volume: -63.4 dB\nmax_volume: -40.0 dB\n"

    monkeypatch.setattr(vts.shutil, "which", lambda _n: "ffmpeg")
    monkeypatch.setattr(vts.subprocess, "run", lambda *a, **k: _Proc())

    assert vts._mean_volume_db(Path(tmp_path / "a.ogg")) == pytest.approx(-63.4)


def test_mean_volume_is_none_when_ffmpeg_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(vts.shutil, "which", lambda _n: None)

    assert vts._mean_volume_db(Path(tmp_path / "a.ogg")) is None
