"""Layer C: conservative interpretation — preserve raw transcript, infer separately."""

from __future__ import annotations

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
)
from app.abuu.voice_interpretation.domain_lexicon import detect_allergy_uncertainty
from app.abuu.voice_interpretation.fuzzy_match import best_fuzzy_match
from app.abuu.voice_interpretation.menu_vocabulary import build_menu_haystack
from app.abuu.waiter.ordering_policy import (
    extract_food_query,
    food_categories,
    has_strong_food_signal,
    proteins_conflict,
    should_block_turn_for_clarification,
)
from app.abuu.waiter.protected_lexicon import (
    category_hints_for_text,
    conservative_transcript,
    detect_protected_tokens,
)
from app.abuu.waiter.trace import trace
from app.core.config import get_settings

STT_CLARIFY_MESSAGE_AR = "ما سمعتك منيح — ممكن تعيد أو تكتب طلبك؟ 🙏"
STT_CLARIFY_MESSAGE_EN = "I didn't catch that clearly — could you repeat or type your order? 🙏"


@dataclass
class InterpretationResult:
    raw_transcript: str
    normalized_transcript: str
    protected_tokens: list[str] = field(default_factory=list)
    category_hints: list[str] = field(default_factory=list)
    menu_match_candidates: list[dict[str, Any]] = field(default_factory=list)
    final_inferred_intent: str | None = None
    inferred_item_query: str | None = None
    confidence: float = 0.0
    stt_confidence: float = 0.0
    needs_clarification: bool = False
    clarification_prompt: str | None = None
    clarification_reason: str | None = None
    allergy_uncertain: bool = False
    source: str = "protected_lexicon"

    @property
    def corrected_transcript(self) -> str:
        """Text passed to intent router — equals normalized, not category-overwritten."""
        return self.normalized_transcript

    def should_block_turn(self) -> bool:
        return should_block_turn_for_clarification(
            reason=self.clarification_reason,
            protected_tokens=self.protected_tokens,
            category_hints=self.category_hints,
            stt_confidence=self.stt_confidence,
        )

    def to_context_json(self) -> dict[str, Any]:
        return {
            "raw_transcript": self.raw_transcript,
            "normalized_transcript": self.normalized_transcript,
            "corrected_transcript": self.corrected_transcript,
            "protected_tokens": self.protected_tokens,
            "category_hints": self.category_hints,
            "inferred_categories": self.category_hints,
            "inferred_item_query": self.inferred_item_query,
            "menu_match_candidates": self.menu_match_candidates[:5],
            "confidence": self.confidence,
            "stt_confidence": self.stt_confidence,
            "needs_clarification": self.needs_clarification,
            "clarification_reason": self.clarification_reason,
            "allergy_uncertain": self.allergy_uncertain,
            "source": self.source,
        }


class WaiterInterpretation:
    @staticmethod
    def interpret(
        abuu_db: Session,
        main_db: Session,
        *,
        transcript: str,
        stt_confidence: float = 0.0,
        session: AgentSession | None = None,
        customer=None,
        lang: str = "ar",
        is_voice: bool = False,
        stt_needs_clarification: bool = False,
    ) -> InterpretationResult:
        raw = str(transcript or "").strip()
        normalized = conservative_transcript(raw, language=lang)
        protected = detect_protected_tokens(normalized, language=lang)
        hints = category_hints_for_text(normalized, language=lang)
        for extra in match_food_categories(normalized):
            if extra not in hints:
                hints.append(extra)
        for extra in expand_food_categories(normalized):
            if extra not in hints:
                hints.append(extra)
        hints = food_categories(hints) or hints

        settings = get_settings()
        restaurant_id = session.restaurant_id if session else None
        haystack = build_menu_haystack(abuu_db, restaurant_id, customer=customer)
        menu_query = extract_food_query(normalized, protected_tokens=protected, category_hints=hints)
        min_score = int(settings.abuu_voice_menu_fuzzy_min_score)
        best_item, best_score, ranked = best_fuzzy_match(
            menu_query, haystack, language=lang, min_score=min_score
        )
        candidates = [{"id": r[0].get("id"), "name": r[0].get("name"), "score": r[1]} for r in ranked[:5]]
        menu_conf = best_score / 100.0 if best_score else 0.0
        inferred_item = None
        if best_item:
            inferred_item = str(best_item.get("name_ar") or best_item.get("name_en") or "")

        intent_conf = 0.88 if len(hints) == 1 else (0.75 if hints else 0.4)
        if best_score >= 70:
            intent_conf = max(intent_conf, 0.85)
        if has_strong_food_signal(
            protected_tokens=protected,
            category_hints=hints,
            stt_confidence=stt_confidence,
        ):
            intent_conf = max(intent_conf, 0.88)

        allergy_uncertain = detect_allergy_uncertainty(normalized) if is_voice or "حساس" in normalized else False
        combined = combined_intent_confidence(
            stt_confidence=float(stt_confidence or 0.0),
            correction_confidence=0.7 if protected else 0.5,
            intent_confidence=intent_conf,
            menu_match_confidence=menu_conf,
        )

        needs_clarification = False
        clarification_prompt: str | None = None
        clarification_reason: str | None = None

        word_count = len(normalized.split())
        clarification_count = int((session.context or {}).get("clarification_count") or 0) if session else 0
        skip_clarify = word_count <= 10 or clarification_count >= 1

        if stt_needs_clarification and is_voice and clarification_count == 0:
            needs_clarification = True
            clarification_reason = "stt_low_quality"
            clarification_prompt = STT_CLARIFY_MESSAGE_AR if lang.startswith("ar") else STT_CLARIFY_MESSAGE_EN
        elif allergy_uncertain and not skip_clarify:
            needs_clarification = True
            clarification_reason = "allergy_uncertain"
            clarification_prompt = allergy_clarification(lang=lang)
        elif proteins_conflict(hints) and not skip_clarify:
            needs_clarification = True
            clarification_reason = "category_ambiguous"
            clarification_prompt = category_clarification(
                [c for c in hints if c in {"chicken", "fish", "meat"}][:2] or hints,
                lang=lang,
            )
        elif (
            not skip_clarify
            and len(ranked) >= 2
            and menu_candidates_ambiguous(ranked[0][1] / 100.0, ranked[1][1] / 100.0)
        ):
            if not has_strong_food_signal(
                protected_tokens=protected,
                category_hints=hints,
                stt_confidence=stt_confidence,
            ):
                a = str(ranked[0][0].get("name_ar") or ranked[0][0].get("name_en") or "")
                b = str(ranked[1][0].get("name_ar") or ranked[1][0].get("name_en") or "")
                needs_clarification = True
                clarification_reason = "item_ambiguous"
                clarification_prompt = item_clarification(a, b, lang=lang)
        elif (
            not skip_clarify
            and is_voice
            and should_clarify(
                combined,
                clarify_threshold=float(settings.abuu_voice_intent_clarify_threshold),
                strong_threshold=float(settings.abuu_voice_intent_strong_threshold),
            )
        ):
            if not has_strong_food_signal(
                protected_tokens=protected,
                category_hints=hints,
                stt_confidence=stt_confidence,
            ) and not food_categories(hints):
                needs_clarification = True
                clarification_reason = "low_confidence"
                clarification_prompt = category_clarification(hints or ["unknown"], lang=lang)

        ctx = session.context if session else {}
        if ctx.get("voice_clarification_sent") and not allergy_uncertain:
            needs_clarification = False
            clarification_prompt = None
            clarification_reason = None
        if clarification_count >= 1 and not allergy_uncertain:
            needs_clarification = False
            clarification_prompt = None
            clarification_reason = None

        result = InterpretationResult(
            raw_transcript=raw,
            normalized_transcript=normalized,
            protected_tokens=protected,
            category_hints=hints,
            menu_match_candidates=candidates,
            final_inferred_intent="food_search" if hints else None,
            inferred_item_query=inferred_item,
            confidence=combined,
            stt_confidence=float(stt_confidence or 0.0),
            needs_clarification=needs_clarification,
            clarification_prompt=clarification_prompt,
            clarification_reason=clarification_reason,
            allergy_uncertain=allergy_uncertain,
        )
        trace(
            "INTERPRET",
            raw=raw,
            normalized=normalized,
            protected=protected,
            hints=hints,
            menu_query=menu_query,
            confidence=combined,
            needs_clarification=needs_clarification,
            clarification_reason=clarification_reason,
            strong_food_signal=has_strong_food_signal(
                protected_tokens=protected,
                category_hints=hints,
                stt_confidence=stt_confidence,
            ),
        )
        return result
