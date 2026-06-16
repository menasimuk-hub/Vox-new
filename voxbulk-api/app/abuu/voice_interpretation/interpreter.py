"""VoiceInterpretationService — thin adapter over waiter conservative interpretation."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.voice_interpretation.logging_utils import log_voice_interpretation
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class VoiceInterpretationResult:
    raw_transcript: str
    normalized_transcript: str
    corrected_transcript: str
    inferred_categories: list[str] = field(default_factory=list)
    inferred_item_query: str | None = None
    stt_confidence: float = 0.0
    correction_confidence: float = 0.0
    intent_confidence: float = 0.0
    menu_match_confidence: float = 0.0
    needs_clarification: bool = False
    clarification_prompt: str | None = None
    clarification_reason: str | None = None
    allergy_uncertain: bool = False
    source: str = "lexicon"

    def to_context_json(self) -> dict[str, Any]:
        return {
            "raw_transcript": self.raw_transcript,
            "normalized_transcript": self.normalized_transcript,
            "corrected_transcript": self.corrected_transcript,
            "inferred_categories": self.inferred_categories,
            "inferred_item_query": self.inferred_item_query,
            "stt_confidence": self.stt_confidence,
            "correction_confidence": self.correction_confidence,
            "intent_confidence": self.intent_confidence,
            "menu_match_confidence": self.menu_match_confidence,
            "needs_clarification": self.needs_clarification,
            "clarification_reason": self.clarification_reason,
            "allergy_uncertain": self.allergy_uncertain,
            "source": self.source,
        }


class VoiceInterpretationService:
    @staticmethod
    def enabled() -> bool:
        return bool(get_settings().abuu_voice_interpretation_enabled)

    @staticmethod
    def interpret(
        abuu_db: Session,
        main_db: Session,
        *,
        transcript: str,
        stt_confidence: float,
        session: AgentSession | None = None,
        customer=None,
        lang: str = "ar",
    ) -> VoiceInterpretationResult:
        from app.abuu.waiter.interpretation import WaiterInterpretation

        waiter = WaiterInterpretation.interpret(
            abuu_db,
            main_db,
            transcript=transcript,
            stt_confidence=float(stt_confidence or 0.0),
            session=session,
            customer=customer,
            lang=lang,
            is_voice=True,
        )
        menu_conf = 0.0
        if waiter.menu_match_candidates:
            menu_conf = float(waiter.menu_match_candidates[0].get("score") or 0) / 100.0
        return VoiceInterpretationResult(
            raw_transcript=waiter.raw_transcript,
            normalized_transcript=waiter.normalized_transcript,
            corrected_transcript=waiter.corrected_transcript,
            inferred_categories=list(waiter.category_hints),
            inferred_item_query=waiter.inferred_item_query,
            stt_confidence=waiter.stt_confidence,
            correction_confidence=0.7 if waiter.protected_tokens else 0.5,
            intent_confidence=waiter.confidence,
            menu_match_confidence=menu_conf,
            needs_clarification=waiter.needs_clarification,
            clarification_prompt=waiter.clarification_prompt,
            clarification_reason=waiter.clarification_reason,
            allergy_uncertain=waiter.allergy_uncertain,
            source=waiter.source,
        )

    @staticmethod
    def log_internal(result: VoiceInterpretationResult) -> None:
        log_voice_interpretation(
            {
                "raw": result.raw_transcript,
                "normalized": result.normalized_transcript,
                "corrected": result.corrected_transcript,
                "categories": result.inferred_categories,
                "item_query": result.inferred_item_query,
                "stt_confidence": result.stt_confidence,
                "correction_confidence": result.correction_confidence,
                "intent_confidence": result.intent_confidence,
                "menu_match_confidence": result.menu_match_confidence,
                "needs_clarification": result.needs_clarification,
                "clarification_reason": result.clarification_reason,
                "allergy_uncertain": result.allergy_uncertain,
                "source": result.source,
            }
        )

    @staticmethod
    def _deepseek_recovery(
        main_db: Session,
        *,
        raw: str,
        normalized: str,
        corrected: str,
        menu_candidates: list[dict[str, Any]],
        lang: str,
    ) -> dict[str, Any] | None:
        import os

        if str(os.getenv("ABUU_DEEPSEEK_ENABLED", "true")).lower() in {"0", "false", "no"}:
            return None
        try:
            from app.services.agents.base import AgentMessage
            from app.services.providers.openai_service import OpenAIProviderService

            block = json.dumps(
                {
                    "raw": raw,
                    "normalized": normalized,
                    "corrected": corrected,
                    "language": lang,
                    "menu_candidates": [
                        {
                            "name_ar": c.get("name_ar"),
                            "name_en": c.get("name_en"),
                            "category": c.get("category"),
                        }
                        for c in menu_candidates
                    ],
                },
                ensure_ascii=False,
            )
            prompt = (
                "Fix noisy Arabic/English food-order STT. Return JSON only: "
                '{"corrected":"","categories":[],"item_query":"","confidence":0.0}'
            )
            result = OpenAIProviderService.complete(
                main_db,
                system_prompt=prompt,
                messages=[AgentMessage(role="user", content=block)],
                max_tokens=200,
                temperature=0.1,
                provider="deepseek",
            )
            raw_out = str(result.assistant_text or "").strip()
            if raw_out.startswith("```"):
                raw_out = re.sub(r"^```(?:json)?\s*", "", raw_out)
                raw_out = re.sub(r"\s*```$", "", raw_out)
            parsed = json.loads(raw_out)
            if float(parsed.get("confidence") or 0) < 0.45:
                return None
            return parsed
        except Exception:
            logger.warning("abuu_voice_deepseek_recovery_failed", exc_info=True)
            return None
