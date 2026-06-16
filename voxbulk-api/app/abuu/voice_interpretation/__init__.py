"""Post-STT voice interpretation for Abuu Arabic food ordering.

Product rule: raw STT transcript is only an input signal, not final customer intent.
Abuu must normalize and interpret Arabic food-ordering speech against menu vocabulary
before deciding how to respond.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["VoiceInterpretationResult", "VoiceInterpretationService"]

if TYPE_CHECKING:
    from app.abuu.voice_interpretation.interpreter import VoiceInterpretationResult, VoiceInterpretationService


def __getattr__(name: str):
    if name in {"VoiceInterpretationResult", "VoiceInterpretationService"}:
        from app.abuu.voice_interpretation import interpreter as mod

        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
