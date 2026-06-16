"""Food query synonym map + DeepSeek expansion before menu search."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

UNKNOWN_QUERY_REPLY_AR = "مش فاهمك منيح — قولنا شو بدك تاكل؟ 🙏"
_UNKNOWN_TOKEN = "UNKNOWN"

QUERY_EXPANSION_SYSTEM_PROMPT = """أنت مساعد فهم طلبات طعام. تستقبل رسائل من عملاء بلهجة 
فلسطينية أردنية أو عربية عامية أو فيها أخطاء إملائية.
مهمتك تحويل الطلب لاسم الأكل الفصيح الصحيح.

قواعد صارمة:
- أرجع فقط اسم الأكل بالعربي الفصيح بكلمة أو كلمتين
- لا شرح ولا جمل — اسم الأكل فقط
- إذا ما فهمت الطلب أرجع: UNKNOWN

أمثلة:
جاج = دجاج
جاجة = دجاج  
فروج = دجاج
چكن = دجاج
chicken = دجاج
شاورمة = شاورما
شاور ما = شاورما
شاور = شاورما
بيتزه = بيتزا
برقر = برغر
هامبرغر = برغر
سمج = سمك
لحمه = لحم
فلافه = فلافل
كبه = كبة
منسف = منسف
مقلوبه = مقلوبة
رز = أرز
بطاطا = بطاطس
بطاطس محمرة = بطاطس مقلية
كولا = كوكاكولا
بيبسي = بيبسي
مي = ماء
عصير بر = عصير برتقال
ايس كريم = آيس كريم
حلو = حلويات"""

FOOD_QUERY_SYNONYMS: dict[str, str] = {
    "جاج": "دجاج",
    "جاجة": "دجاج",
    "فروج": "دجاج",
    "چكن": "دجاج",
    "chicken": "دجاج",
    "شاورمة": "شاورما",
    "شاور": "شاورما",
    "بيتزه": "بيتزا",
    "بيتزة": "بيتزا",
    "برقر": "برغر",
    "هامبرغر": "برغر",
    "سمج": "سمك",
    "لحمه": "لحم",
    "فلافه": "فلافل",
    "كبه": "كبة",
    "مقلوبه": "مقلوبة",
    "بطاطا": "بطاطس",
    "مي": "ماء",
    "fish": "سمك",
    "meat": "لحم",
    "pizza": "بيتزا",
    "burger": "برغر",
    "salad": "سلطة",
    "rice": "أرز",
    "ruz": "أرز",
}

_SYNONYM_KEYS_LOWER = {k.lower(): v for k, v in FOOD_QUERY_SYNONYMS.items()}


@dataclass(frozen=True)
class QueryExpansionResult:
    raw: str
    synonym_text: str
    expanded: str
    unknown: bool = False
    ai_used: bool = False
    ai_failed: bool = False


def apply_food_synonyms(text: str) -> str:
    """Map dialect/typo tokens to normalized Arabic food names."""
    raw = str(text or "").strip()
    if not raw:
        return raw

    lowered_full = raw.lower()
    if lowered_full in _SYNONYM_KEYS_LOWER:
        return _SYNONYM_KEYS_LOWER[lowered_full]

    tokens = re.split(r"\s+", raw)
    mapped: list[str] = []
    changed = False
    for token in tokens:
        key = token.lower()
        if key in _SYNONYM_KEYS_LOWER:
            mapped.append(_SYNONYM_KEYS_LOWER[key])
            changed = True
        else:
            mapped.append(token)
    if changed:
        return " ".join(mapped).strip()
    return raw


def expand_food_query(main_db: Session, *, raw: str) -> QueryExpansionResult:
    """Synonym normalize then DeepSeek-expand; fail-open on AI errors."""
    raw_text = str(raw or "").strip()
    synonym_text = apply_food_synonyms(raw_text)

    if not raw_text:
        return QueryExpansionResult(
            raw=raw_text,
            synonym_text=synonym_text,
            expanded=synonym_text,
            unknown=True,
        )

    try:
        from app.abuu.waiter.deepseek_client import WaiterDeepSeekClient

        result = WaiterDeepSeekClient.complete(
            main_db,
            system_prompt=QUERY_EXPANSION_SYSTEM_PROMPT,
            user_content=f"شو يقصد العميل بـ: {raw_text}",
            max_tokens=20,
            temperature=0.0,
        )
        if result.fallback_used or not str(result.text or "").strip():
            logger.warning(
                "abuu_query_expansion_failed | raw=%r error=%r",
                raw_text,
                result.error,
            )
            logger.info(
                "abuu_query_expansion | raw=%r expanded=%r",
                raw_text,
                synonym_text,
            )
            return QueryExpansionResult(
                raw=raw_text,
                synonym_text=synonym_text,
                expanded=synonym_text,
                ai_failed=True,
            )

        expanded = str(result.text or "").strip()
        if not expanded or expanded.upper() == _UNKNOWN_TOKEN:
            logger.info(
                "abuu_query_expansion | raw=%r expanded=UNKNOWN",
                raw_text,
            )
            return QueryExpansionResult(
                raw=raw_text,
                synonym_text=synonym_text,
                expanded=synonym_text,
                unknown=True,
                ai_used=True,
            )

        logger.info(
            "abuu_query_expansion | raw=%r expanded=%r",
            raw_text,
            expanded,
        )
        return QueryExpansionResult(
            raw=raw_text,
            synonym_text=synonym_text,
            expanded=expanded,
            ai_used=True,
        )
    except Exception as exc:
        logger.warning(
            "abuu_query_expansion_failed | raw=%r error=%r",
            raw_text,
            str(exc),
        )
        logger.info(
            "abuu_query_expansion | raw=%r expanded=%r",
            raw_text,
            synonym_text,
        )
        return QueryExpansionResult(
            raw=raw_text,
            synonym_text=synonym_text,
            expanded=synonym_text,
            ai_failed=True,
        )


def expansion_context_payload(result: QueryExpansionResult) -> dict[str, str | bool]:
    return {
        "raw": result.raw,
        "synonym_text": result.synonym_text,
        "expanded": result.expanded,
        "unknown": result.unknown,
        "ai_used": result.ai_used,
        "ai_failed": result.ai_failed,
    }


def get_cached_expansion(session, raw: str) -> QueryExpansionResult | None:
    ctx = (getattr(session, "context", None) or {}).get("last_query_expansion")
    if not isinstance(ctx, dict):
        return None
    if str(ctx.get("raw") or "").strip() != str(raw or "").strip():
        return None
    return QueryExpansionResult(
        raw=str(ctx.get("raw") or ""),
        synonym_text=str(ctx.get("synonym_text") or ""),
        expanded=str(ctx.get("expanded") or ""),
        unknown=bool(ctx.get("unknown")),
        ai_used=bool(ctx.get("ai_used")),
        ai_failed=bool(ctx.get("ai_failed")),
    )


def resolve_search_query(session, main_db: Session | None, *, raw: str) -> QueryExpansionResult:
    """Use cached expansion, else AI (if main_db), else synonyms only."""
    raw_text = str(raw or "").strip()
    cached = get_cached_expansion(session, raw_text) if session is not None else None
    if cached is not None:
        return cached
    if main_db is None:
        synonym_text = apply_food_synonyms(raw_text)
        return QueryExpansionResult(
            raw=raw_text,
            synonym_text=synonym_text,
            expanded=synonym_text,
        )
    result = expand_food_query(main_db, raw=raw_text)
    if session is not None:
        session.context = dict(getattr(session, "context", None) or {})
        session.context["last_query_expansion"] = expansion_context_payload(result)
    return result


def intent_with_expansion(intent, expansion: QueryExpansionResult):
    """Merge expanded text into AbuuIntent categories and item_query."""
    from app.abuu.conversation.intent_router import AbuuIntent
    from app.abuu.menu_intelligence.arabic_lexicon import expand_food_categories
    from app.abuu.services.preference_service import match_food_categories

    expanded = str(expansion.expanded or "").strip()
    categories = list(intent.categories or [])
    for cat in match_food_categories(expanded):
        if cat not in categories:
            categories.append(cat)
    for cat in expand_food_categories(expanded):
        if cat not in categories:
            categories.append(cat)
    return AbuuIntent(
        name=intent.name,
        categories=categories,
        item_query=expanded or intent.item_query,
        confidence=intent.confidence,
        source="query_expansion" if expansion.ai_used else intent.source,
    )
