from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.voice_agent_service import AzureSpeechService, AzureSpeechSynthesisError, VoiceAgentConfigError


class AzureSpeechProviderService(AzureSpeechService):
    """Azure Speech provider facade used by the voice-agent runtime."""

    @staticmethod
    def synthesize_text_result(
        db: Session,
        *,
        text: str,
        voice_id: str | None = None,
        output_format: str = "telephony",
        use_ssml: bool = True,
        speaking_rate: str | None = None,
    ) -> dict[str, Any]:
        """
        Return raw audio bytes on success, or Azure cancellation details on failure.

        The JSON-facing admin smoke route removes raw audio_data before returning.
        """
        return AzureSpeechService.synthesize_text_result(
            db,
            text=text,
            voice_id=voice_id,
            output_format=output_format,
            use_ssml=use_ssml,
            speaking_rate=speaking_rate,
        )


__all__ = ["AzureSpeechProviderService", "AzureSpeechService", "AzureSpeechSynthesisError", "VoiceAgentConfigError"]
