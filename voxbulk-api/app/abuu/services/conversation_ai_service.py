"""DeepSeek skill classification for Abuu WhatsApp agent."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.services.intent_service import detect_intent, is_abuu_start_message, is_restaurant_list_message, is_show_more_message
from app.abuu.services.kb_service import detect_kb_topic
from app.abuu.services.preference_service import match_food_categories
from app.abuu.services.skill_definitions import (
    SKILL_ANSWER_KB,
    SKILL_BUILD_CART,
    SKILL_CANCEL_OR_REFUND,
    SKILL_CAPTURE_LOCATION,
    SKILL_CAPTURE_NAME,
    SKILL_CONFIRM_ORDER,
    SKILL_GREET_CUSTOMER,
    SKILL_HANDOFF_TO_ADMIN,
    SKILL_MENU_RECOMMEND,
    SKILL_ORDER_STATUS,
    SKILL_RESTAURANT_SEARCH,
)
from app.services.providers.openai_service import OpenAIProviderService
from app.services.agents.base import AgentMessage

logger = logging.getLogger(__name__)

_CLASSIFY_PROMPT = """You classify WhatsApp food-order messages for Abuu delivery.
Return ONLY valid JSON with keys: skill, categories, item_query, kb_topic, restaurant_ref, confidence, clarification.
Allowed skills: greet_customer, capture_name, capture_location, restaurant_search, menu_recommend, build_cart, confirm_order, cancel_or_refund, order_status, answer_kb, handoff_to_admin.
Allowed categories: chicken, fish, meat, salad, drinks, dessert, vegetarian, chips.
Allowed kb_topic: hours, delivery_hours, delivery_zone, prep_time, minimum_order, delivery_fee, payment_methods, refund, cancellation, allergens, escalation, holiday.
Never invent menu items or policy facts. Use null when unsure. confidence is 0-1."""


@dataclass(frozen=True)
class SkillClassification:
    skill: str
    categories: list[str]
    item_query: str | None = None
    kb_topic: str | None = None
    restaurant_ref: str | None = None
    confidence: float = 0.0
    clarification: str | None = None
    source: str = "regex"


def _deepseek_enabled() -> bool:
    flag = str(os.getenv("ABUU_DEEPSEEK_ENABLED", "true")).lower()
    return flag not in {"0", "false", "no"}


def _parse_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def classify_regex(
    text: str,
    *,
    step: str | None,
    has_session: bool,
) -> SkillClassification:
    normalized = str(text or "").strip()
    if is_abuu_start_message(normalized):
        return SkillClassification(skill=SKILL_GREET_CUSTOMER, categories=[], confidence=0.95, source="regex")

    intent = detect_intent(normalized, has_active_session=has_session, step=step)

    if intent.name == "order_food":
        return SkillClassification(skill=SKILL_GREET_CUSTOMER, categories=[], confidence=0.9, source="regex")
    if step == "awaiting_name" and intent.name == "provide_name":
        return SkillClassification(skill=SKILL_CAPTURE_NAME, categories=[], confidence=0.95, source="regex")
    if step == "choosing_restaurant" and re.fullmatch(r"\d{1,2}", normalized):
        return SkillClassification(
            skill=SKILL_RESTAURANT_SEARCH,
            categories=[],
            restaurant_ref=normalized,
            confidence=0.95,
            source="regex",
        )
    if intent.name == "cancel":
        return SkillClassification(skill=SKILL_CANCEL_OR_REFUND, categories=[], confidence=0.95, source="regex")
    if intent.name == "confirm":
        return SkillClassification(skill=SKILL_CONFIRM_ORDER, categories=[], confidence=0.95, source="regex")
    if is_restaurant_list_message(normalized):
        return SkillClassification(skill=SKILL_RESTAURANT_SEARCH, categories=[], confidence=0.9, source="regex")
    if is_show_more_message(normalized):
        return SkillClassification(skill=SKILL_RESTAURANT_SEARCH, categories=[], confidence=0.85, source="regex")
    if step == "awaiting_delivery" and normalized and intent.name not in {"cancel", "confirm", "menu"}:
        return SkillClassification(skill=SKILL_CAPTURE_LOCATION, categories=[], confidence=0.9, source="regex")

    kb_topic = detect_kb_topic(normalized)
    if kb_topic:
        return SkillClassification(skill=SKILL_ANSWER_KB, categories=[], kb_topic=kb_topic, confidence=0.85, source="regex")

    if intent.name == "order_status":
        return SkillClassification(skill=SKILL_ORDER_STATUS, categories=[], confidence=0.9, source="regex")

    categories = match_food_categories(normalized)
    if categories and step in {None, "awaiting_preference", "browsing", "choosing_restaurant"}:
        return SkillClassification(skill=SKILL_MENU_RECOMMEND, categories=categories, confidence=0.85, source="regex")

    if has_session and normalized:
        if intent.name == "add_item":
            return SkillClassification(
                skill=SKILL_BUILD_CART,
                categories=[],
                item_query=intent.item_ref or normalized,
                confidence=0.8,
                source="regex",
            )
        if detect_kb_topic(normalized) is None and any(
            w in normalized.lower() for w in ("help", "manager", "support", "complaint", "مدير", "دعم")
        ):
            return SkillClassification(skill=SKILL_HANDOFF_TO_ADMIN, categories=[], confidence=0.7, source="regex")

    return SkillClassification(skill=SKILL_BUILD_CART, categories=[], item_query=normalized, confidence=0.4, source="regex")


_ORDER_STEPS = frozenset(
    {"awaiting_name", "awaiting_preference", "choosing_restaurant", "browsing", "awaiting_delivery", "awaiting_substitution"}
)


def classify_turn(
    main_db: Session,
    *,
    text: str,
    step: str | None,
    has_session: bool,
    lang: str,
    session_context: dict | None = None,
) -> SkillClassification:
    regex_result = classify_regex(text, step=step, has_session=has_session)
    if not _deepseek_enabled() or not str(text or "").strip():
        return regex_result

    # Fast path: structured ordering steps and confident regex — skip extra LLM call.
    if step in _ORDER_STEPS or regex_result.confidence >= 0.85:
        return regex_result

    trivial = regex_result.skill in {
        SKILL_CONFIRM_ORDER,
        SKILL_CANCEL_OR_REFUND,
        SKILL_CAPTURE_NAME,
    } and regex_result.confidence >= 0.9
    if trivial:
        return regex_result

    try:
        user_block = json.dumps(
            {
                "message": text,
                "step": step,
                "has_session": has_session,
                "language": lang,
                "context": session_context or {},
            },
            ensure_ascii=False,
        )
        result = OpenAIProviderService.complete(
            main_db,
            system_prompt=_CLASSIFY_PROMPT,
            messages=[AgentMessage(role="user", content=user_block)],
            max_tokens=300,
            temperature=0.1,
            provider="deepseek",
        )
        parsed = _parse_json(str(result.assistant_text or ""))
        skill = str(parsed.get("skill") or regex_result.skill)
        categories = [str(c) for c in (parsed.get("categories") or []) if c]
        if not categories:
            categories = regex_result.categories
        confidence = float(parsed.get("confidence") or 0.0)
        if confidence < 0.55:
            return regex_result
        return SkillClassification(
            skill=skill,
            categories=categories,
            item_query=parsed.get("item_query") or regex_result.item_query,
            kb_topic=parsed.get("kb_topic") or regex_result.kb_topic,
            restaurant_ref=parsed.get("restaurant_ref"),
            confidence=confidence,
            clarification=parsed.get("clarification"),
            source="deepseek",
        )
    except Exception:
        logger.warning("abuu_skill_classify_fallback", exc_info=True)
        return regex_result
