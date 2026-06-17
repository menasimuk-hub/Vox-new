"""STT provider order documentation and future extension stub."""

from __future__ import annotations

import os

DEFAULT_STT_PROVIDER_ORDER = ("deepgram", "deepinfra", "whisper_cpp", "groq")


def stt_provider_order() -> tuple[str, ...]:
    raw = str(os.getenv("ABUU_VOICE_STT_PROVIDER_ORDER", "") or "").strip()
    if not raw:
        return DEFAULT_STT_PROVIDER_ORDER
    parts = tuple(p.strip().lower() for p in raw.split(",") if p.strip())
    return parts or DEFAULT_STT_PROVIDER_ORDER
