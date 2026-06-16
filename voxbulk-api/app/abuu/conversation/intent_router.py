"""Intent classification for Abuu conversational WhatsApp."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.services.intent_service import (
    detect_intent,
    is_abuu_start_message,
    is_restaurant_list_message,
)
from app.abuu.agent.session_reset import is_offer_query
from app.abuu.services.preference_service import match_food_categories
from app.abuu.menu_intelligence.arabic_lexicon import expand_food_categories
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService

logger = logging.getLogger(__name__)

_FOOD_INTENT_RULE = (
    "If the customer names a food type (دجاج, سمك, لحم, مشروبات, كولا, etc.), "
    "classify as food_search with matching categories. "
    "Do NOT ask them to clarify what they want when the food type is already stated. "
    "Only ask one short question when intent is genuinely ambiguous (e.g. chicken AND fish)."
)

_INTENT_PROMPT = f"""You classify WhatsApp food-order messages for YallaSay Abuu (Gaza delivery).
Return JSON only: {{"intent": "...", "categories": [], "item_query": "", "confidence": 0.0}}

Intents:
- greet (start: yallasay, abuu, hello)
- food_search (user wants food type: fish, chicken, spicy, etc.)
- restaurant_list (ask which restaurants exist)
- menu_browse (show menu)
- offers (deals/promotions)
- select_item (pick specific dish by name)
- cart_modify (add/remove drink, salad, etc.)
- confirm, cancel, address, order_status, support
- restaurant_switch_confirm (user agrees to switch restaurant after conflict)
- restaurant_switch_keep (user keeps current restaurant)

{_FOOD_INTENT_RULE}

Few-shot examples (Palestinian/Jordanian dialect):
- "أهلين" → greet
- "شو في عندكم" → menu_browse
- "بدي دجاج" → food_search, categories: ["chicken"]
- "رقم واحد" / "1" → select_item
- "تمام يلا" → confirm
- "عنواني شارع..." → address

Arabic, English, and mixed Arabizi supported."""


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(p in text for p in phrases)


_GREET_PHRASES = (
    "أهلين",
    "هلا",
    "مرحبا",
    "السلام عليكم",
    "هاي",
    "كيفك",
    "في حدا",
    "هلو",
)

_MENU_BROWSE_PHRASES = (
    "شو في عندكم",
    "شو عندكم",
    "بدي اشوف القائمة",
    "شو منيح عندكم",
    "شو في اكل",
    "عرضولي الاكل",
    "شو الاكل",
    "بدي اعرف شو في",
    "شو الموجود",
    "شو بتعملوا",
)

_FOOD_SEARCH_PHRASES = (
    "بدي دجاج",
    "بدي لحمة",
    "بدي بيتزا",
    "بدي شاورما",
    "بدي فلافل",
    "ابي اكل",
    "بدي اكل",
    "حابب اطلب",
    "بدي اطلب",
    "في عندكم",
    "بدي منسف",
    "بدي كبسة",
    "بدي مقلوبة",
    "شو عندكم من الدجاج",
    "شو عندكم من اللحمة",
)

_SELECT_ITEM_PHRASES = (
    "هاد",
    "هاي",
    "الاول",
    "الثاني",
    "الثالث",
    "رقم واحد",
    "رقم اثنين",
    "رقم تلاتة",
    "اختار",
    "بدي هاد",
    "خد هاد",
    "نفس الشي",
    "نفس الطلب",
    "نفس الي",
    "هاد المنيح",
)

_CONFIRM_PHRASES = (
    "اه",
    "تمام",
    "يلا",
    "ماشي",
    "اوكي",
    "كويس",
    "خلص",
    "هيك",
    "صح",
    "نعم",
    "اطلب",
    "اكيد",
    "يلا اطلب",
)

_ADDRESS_PHRASES = (
    "عنواني",
    "انا في",
    "موقعي",
    "بعتلك الموقع",
    "هون",
    "حارة",
    "شارع",
    "بناية",
    "دور",
    "شقة",
)


@dataclass
class AbuuIntent:
    name: str
    categories: list[str] = field(default_factory=list)
    item_query: str | None = None
    confidence: float = 0.85
    source: str = "regex"


def _deepseek_intent_enabled() -> bool:
    flag = str(os.getenv("ABUU_DEEPSEEK_ENABLED", "true")).lower()
    return flag not in {"0", "false", "no"}


def _regex_intent(text: str, session: AgentSession, pre_inferred: dict[str, Any] | None = None) -> AbuuIntent:
    from app.abuu.voice_interpretation.normalize import normalize_ordering_text

    normalized = normalize_ordering_text(text, language=session.language or "ar")
    ctx = session.context or {}

    if pre_inferred:
        pre_cats = [str(c) for c in (pre_inferred.get("inferred_categories") or []) if c]
        pre_conf = float(pre_inferred.get("intent_confidence") or 0.0)
        if pre_cats and pre_conf >= 0.72:
            return AbuuIntent(
                "food_search",
                categories=pre_cats,
                item_query=pre_inferred.get("inferred_item_query"),
                confidence=max(0.88, pre_conf),
                source="voice_interpretation",
            )

    if ctx.get("pending_restaurant_switch"):
        low = normalized.lower()
        if any(w in low for w in ("switch", "غيّر", "غير", "change", "بدّل", "بدل")):
            return AbuuIntent("restaurant_switch_confirm", confidence=0.95)
        if any(w in low for w in ("keep", "خلي", "لا", "same", "stay", "no")):
            return AbuuIntent("restaurant_switch_keep", confidence=0.95)

    if _contains_any(normalized, _GREET_PHRASES) or is_abuu_start_message(normalized):
        return AbuuIntent("greet", confidence=0.95)

    if _contains_any(normalized, _ADDRESS_PHRASES):
        return AbuuIntent("address", confidence=0.9)

    if _contains_any(normalized, _CONFIRM_PHRASES):
        return AbuuIntent("confirm", confidence=0.95)

    if re.fullmatch(r"[1-9]\d?", normalized.strip()):
        return AbuuIntent("select_item", item_query=normalized.strip(), confidence=0.92)

    if _contains_any(normalized, _SELECT_ITEM_PHRASES):
        last_added = ctx.get("last_added_item") or {}
        if _contains_any(normalized, ("نفس الشي", "نفس الطلب", "نفس الي")) and last_added.get("name"):
            return AbuuIntent(
                "select_item",
                item_query=str(last_added.get("name") or ""),
                confidence=0.9,
                source="repeat_order",
            )
        return AbuuIntent("select_item", item_query=normalized, confidence=0.88)

    if _contains_any(normalized, _MENU_BROWSE_PHRASES):
        return AbuuIntent("menu_browse", confidence=0.9)

    if _contains_any(normalized, _FOOD_SEARCH_PHRASES):
        categories = match_food_categories(normalized)
        for extra in expand_food_categories(normalized):
            if extra not in categories:
                categories.append(extra)
        return AbuuIntent(
            "food_search",
            categories=categories,
            item_query=normalized,
            confidence=0.9,
        )

    intent = detect_intent(normalized, has_active_session=bool(session.active_order_id), step=None)
    if intent.name == "confirm":
        return AbuuIntent("confirm", confidence=0.95)
    if intent.name == "cancel":
        return AbuuIntent("cancel", confidence=0.95)
    if intent.name == "order_status":
        return AbuuIntent("order_status", confidence=0.9)

    if is_restaurant_list_message(normalized):
        return AbuuIntent("restaurant_list", confidence=0.9)

    if is_offer_query(normalized):
        return AbuuIntent("offers", confidence=0.9)

    if re.search(r"(?i)\b(menu|منيو|قائمة)\b", normalized):
        return AbuuIntent("menu_browse", confidence=0.85)

    categories = match_food_categories(normalized)
    for extra in expand_food_categories(normalized):
        if extra not in categories:
            categories.append(extra)
    if "offers" in categories:
        return AbuuIntent("offers", confidence=0.9)
    if categories:
        return AbuuIntent("food_search", categories=categories, confidence=0.88)

    if any(w in normalized.lower() for w in ("help", "manager", "support", "مدير", "دعم")):
        return AbuuIntent("support", confidence=0.8)

    if session.restaurant_id and len(normalized) > 2:
        return AbuuIntent("select_item", item_query=normalized, confidence=0.6)

    return AbuuIntent("food_search", item_query=normalized, confidence=0.4)


class IntentRouter:
    @staticmethod
    def classify(main_db: Session, text: str, session: AgentSession) -> AbuuIntent:
        pre = (session.context or {}).get("voice_interpretation")
        regex = _regex_intent(text, session, pre_inferred=pre if isinstance(pre, dict) else None)
        if regex.confidence >= 0.85 or not _deepseek_intent_enabled():
            return regex

        try:
            block = json.dumps(
                {
                    "message": text,
                    "language": session.language,
                    "restaurant_id": session.restaurant_id,
                    "has_cart": bool(session.cart),
                },
                ensure_ascii=False,
            )
            result = OpenAIProviderService.complete(
                main_db,
                system_prompt=_INTENT_PROMPT,
                messages=[AgentMessage(role="user", content=block)],
                max_tokens=200,
                temperature=0.1,
                provider="deepseek",
            )
            raw = str(result.assistant_text or "").strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            name = str(parsed.get("intent") or regex.name)
            cats = [str(c) for c in (parsed.get("categories") or []) if c]
            if not cats:
                cats = regex.categories
            conf = float(parsed.get("confidence") or 0.0)
            if conf < 0.5:
                return regex
            return AbuuIntent(
                name=name,
                categories=cats,
                item_query=parsed.get("item_query") or regex.item_query,
                confidence=conf,
                source="deepseek",
            )
        except Exception:
            logger.warning("abuu_intent_deepseek_fallback", exc_info=True)
            return regex
