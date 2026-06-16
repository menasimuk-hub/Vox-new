"""VoiceInterpretationService — post-STT normalization and intent recovery."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.menu_intelligence.arabic_lexicon import expand_food_categories
from app.abuu.services.preference_service import match_food_categories
from app.abuu.voice_interpretation.clarification import (
    allergy_clarification,
    category_clarification,
    item_clarification,
)
from app.abuu.voice_interpretation.confidence import (
    combined_intent_confidence,
    menu_candidates_ambiguous,
    should_clarify,
    should_proceed,
)
from app.abuu.voice_interpretation.domain_lexicon import detect_allergy_uncertainty, lexicon_correct
from app.abuu.voice_interpretation.fuzzy_match import best_fuzzy_match
from app.abuu.voice_interpretation.logging_utils import log_voice_interpretation
from app.abuu.voice_interpretation.menu_vocabulary import build_menu_haystack
from app.abuu.voice_interpretation.normalize import normalize_ordering_text
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
        settings = get_settings()
        raw = str(transcript or "").strip()
        normalized = normalize_ordering_text(raw, language=lang)
        corrected, lex_categories, correction_conf = lexicon_correct(normalized, language=lang)

        categories = list(lex_categories)
        for extra in match_food_categories(corrected):
            if extra not in categories:
                categories.append(extra)
        for extra in expand_food_categories(corrected):
            if extra not in categories:
                categories.append(extra)

        restaurant_id = session.restaurant_id if session else None
        menu_haystack = build_menu_haystack(abuu_db, restaurant_id, customer=customer)
        min_score = int(settings.abuu_voice_menu_fuzzy_min_score)
        best_item, best_score, ranked = best_fuzzy_match(
            corrected,
            menu_haystack,
            language=lang,
            min_score=min_score,
        )
        menu_conf = best_score / 100.0 if best_score else 0.0
        source = "lexicon"

        inferred_item: str | None = None
        if best_item:
            inferred_item = str(best_item.get("name_ar") or best_item.get("name_en") or "")
            source = "menu_fuzzy"
            cat = str(best_item.get("category") or "").lower()
            if "drink" in cat or "مشرو" in cat:
                if "drinks" not in categories:
                    categories.append("drinks")

        intent_conf = 0.5 if categories else 0.35
        if len(categories) == 1:
            intent_conf = 0.88
        elif categories:
            intent_conf = 0.75
        if best_score >= 70:
            intent_conf = max(intent_conf, 0.85)

        allergy_uncertain = detect_allergy_uncertainty(corrected)
        combined = combined_intent_confidence(
            stt_confidence=float(stt_confidence or 0.0),
            correction_confidence=correction_conf,
            intent_confidence=intent_conf,
            menu_match_confidence=menu_conf,
        )

        needs_clarification = False
        clarification_prompt: str | None = None
        clarification_reason: str | None = None

        if allergy_uncertain:
            needs_clarification = True
            clarification_reason = "allergy_uncertain"
            clarification_prompt = allergy_clarification(lang=lang)

        elif "chicken" in categories and "fish" in categories:
            needs_clarification = True
            clarification_reason = "category_ambiguous"
            clarification_prompt = category_clarification(["chicken", "fish"], lang=lang)

        elif len(ranked) >= 2 and menu_candidates_ambiguous(ranked[0][1] / 100.0, ranked[1][1] / 100.0):
            a = str(ranked[0][0].get("name_ar") or ranked[0][0].get("name_en") or "")
            b = str(ranked[1][0].get("name_ar") or ranked[1][0].get("name_en") or "")
            needs_clarification = True
            clarification_reason = "item_ambiguous"
            clarification_prompt = item_clarification(a, b, lang=lang)

        elif should_clarify(
            combined,
            clarify_threshold=float(settings.abuu_voice_intent_clarify_threshold),
            strong_threshold=float(settings.abuu_voice_intent_strong_threshold),
        ):
            needs_clarification = True
            clarification_reason = "low_confidence"
            clarification_prompt = category_clarification(categories or ["unknown"], lang=lang)

        if (
            not needs_clarification
            and not should_proceed(combined, strong_threshold=float(settings.abuu_voice_intent_strong_threshold))
            and settings.abuu_voice_deepseek_recovery_enabled
        ):
            recovered = VoiceInterpretationService._deepseek_recovery(
                main_db,
                raw=raw,
                normalized=normalized,
                corrected=corrected,
                menu_candidates=[r[0] for r in ranked[:5]],
                lang=lang,
            )
            if recovered:
                corrected = recovered.get("corrected") or corrected
                if recovered.get("categories"):
                    categories = list(recovered["categories"])
                inferred_item = recovered.get("item_query") or inferred_item
                intent_conf = float(recovered.get("confidence") or intent_conf)
                source = "deepseek_recovery"
                combined = combined_intent_confidence(
                    stt_confidence=float(stt_confidence or 0.0),
                    correction_confidence=correction_conf,
                    intent_confidence=intent_conf,
                    menu_match_confidence=menu_conf,
                )
                if should_clarify(
                    combined,
                    clarify_threshold=float(settings.abuu_voice_intent_clarify_threshold),
                    strong_threshold=float(settings.abuu_voice_intent_strong_threshold),
                ):
                    needs_clarification = True
                    clarification_reason = "deepseek_low_confidence"
                    clarification_prompt = category_clarification(categories, lang=lang)

        ctx = session.context if session else {}
        if ctx.get("voice_clarification_sent") and not allergy_uncertain:
            needs_clarification = False
            clarification_prompt = None
            clarification_reason = None

        return VoiceInterpretationResult(
            raw_transcript=raw,
            normalized_transcript=normalized,
            corrected_transcript=corrected or normalized or raw,
            inferred_categories=categories,
            inferred_item_query=inferred_item,
            stt_confidence=float(stt_confidence or 0.0),
            correction_confidence=correction_conf,
            intent_confidence=intent_conf,
            menu_match_confidence=menu_conf,
            needs_clarification=needs_clarification,
            clarification_prompt=clarification_prompt,
            clarification_reason=clarification_reason,
            allergy_uncertain=allergy_uncertain,
            source=source,
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
