"""Code-written Utility WA template content: emoji + buttons + neutral wording (no marketing)."""

from __future__ import annotations

import json
import re
from typing import Any

DEFAULT_EMOJI = "📋"
RATING_BUTTONS = ["Excellent", "Good", "Poor"]
YES_NO_BUTTONS = ["Yes", "No"]
THANKS_BUTTONS = ["Done"]
AR_RATING_BUTTONS = ["ممتاز", "جيد", "ضعيف"]
AR_YES_NO_BUTTONS = ["نعم", "لا"]
AR_THANKS_BUTTONS = ["تم"]

# English marketing signals Meta uses to reclassify Utility → Marketing.
PROMO_WORDS_EN = re.compile(
    r"\b(sale|sales|discount|discounts|offer|offers|gift|gifts|reward|rewards|"
    r"promotion|promotions|promo|promos|deal|deals|loyalty|shop\s*now|see\s*deals|"
    r"join\s*the\s*club|refer\s*a\s*friend|free\s*trial|upgrade|upsell|marketing|"
    r"coupon|vouchers?|bargain|clearance)\b",
    re.I,
)

# Arabic marketing signals.
PROMO_WORDS_AR = re.compile(
    r"(خصم|خصومات|عرض|عروض|هدية|هدايا|مكافأة|مكافات|ترويج|ترويجية|ولاء|"
    r"تسوق\s*الآن|صفقة|صفقات|ترقية|تسويق|كوبون|قسيمة)"
)

# Map risky / English topic names to safe Utility labels (EN + AR).
TOPIC_SAFE_EN: dict[str, str] = {
    "promotions_clarity": "pricing information clarity",
    "promotions clarity": "pricing information clarity",
    "promotion": "pricing information",
    "promotions": "pricing information",
    "discount": "pricing",
    "discounts": "pricing",
    "loyalty programme": "membership experience",
    "loyalty program": "membership experience",
    "loyalty": "membership experience",
    "offer": "service",
    "offers": "service",
    "sale": "purchase",
    "sales": "purchase",
    "gift": "item",
    "reward": "outcome",
    "marketing": "communication",
    "cleanliness": "cleanliness",
    "staff friendliness": "staff friendliness",
    "staff_friendliness": "staff friendliness",
    "overall experience": "overall experience",
    "overall_experience": "overall experience",
    "value for money": "value for money",
    "value_for_money": "value for money",
}

TOPIC_SAFE_AR: dict[str, str] = {
    "promotions_clarity": "وضوح معلومات الأسعار",
    "promotions clarity": "وضوح معلومات الأسعار",
    "promotion": "معلومات الأسعار",
    "promotions": "معلومات الأسعار",
    "discount": "الأسعار",
    "discounts": "الأسعار",
    "loyalty programme": "تجربة العضوية",
    "loyalty program": "تجربة العضوية",
    "loyalty": "تجربة العضوية",
    "offer": "الخدمة",
    "offers": "الخدمة",
    "sale": "الشراء",
    "sales": "الشراء",
    "gift": "المنتج",
    "reward": "النتيجة",
    "marketing": "التواصل",
    "cleanliness": "النظافة",
    "staff friendliness": "ودّ الموظفين",
    "staff_friendliness": "ودّ الموظفين",
    "overall experience": "التجربة العامة",
    "overall_experience": "التجربة العامة",
    "overall experience today": "التجربة العامة اليوم",
    "value for money": "القيمة مقابل السعر",
    "value_for_money": "القيمة مقابل السعر",
    "would recommend": "احتمال التوصية",
    "would_recommend": "احتمال التوصية",
    "return intent": "نية العودة",
    "return_intent": "نية العودة",
    "wait time": "وقت الانتظار",
    "wait_time": "وقت الانتظار",
    "service speed": "سرعة الخدمة",
    "service_speed": "سرعة الخدمة",
    "communication": "التواصل",
    "atmosphere": "الأجواء",
    "food quality": "جودة الطعام",
    "food_quality": "جودة الطعام",
    "booking experience": "تجربة الحجز",
    "booking_experience": "تجربة الحجز",
}


def _norm_topic_key(topic: str | None) -> str:
    return re.sub(r"\s+", " ", str(topic or "").strip().lower().replace("_", " "))


def _has_latin(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text or ""))


def safe_topic_en(topic_name: str | None) -> str:
    raw = str(topic_name or "").strip()
    key = _norm_topic_key(raw)
    if key in TOPIC_SAFE_EN:
        return TOPIC_SAFE_EN[key]
    slug_key = key.replace(" ", "_")
    if slug_key in TOPIC_SAFE_EN:
        return TOPIC_SAFE_EN[slug_key]
    # Strip banned words from topic label.
    cleaned = PROMO_WORDS_EN.sub("service", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip() or "your recent visit"
    if is_promo_wording(cleaned):
        return "your recent visit"
    return cleaned.lower()


def safe_topic_ar(topic_name: str | None) -> str:
    raw = str(topic_name or "").strip()
    key = _norm_topic_key(raw)
    if key in TOPIC_SAFE_AR:
        return TOPIC_SAFE_AR[key]
    slug_key = key.replace(" ", "_")
    if slug_key in TOPIC_SAFE_AR:
        return TOPIC_SAFE_AR[slug_key]
    # Never inject English into Arabic bodies.
    if _has_latin(raw) or is_promo_wording(raw):
        return "هذه الخدمة"
    cleaned = PROMO_WORDS_AR.sub("", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "هذه الخدمة"


def has_leading_emoji(text: str | None) -> bool:
    body = str(text or "").strip()
    if not body:
        return False
    ch = body[0]
    return ord(ch) > 127 or ch in {"✅", "📋", "⭐", "🙏", "💬", "📝", "👍", "👋", "🔔"}


def ensure_leading_emoji(text: str | None, *, emoji: str = DEFAULT_EMOJI) -> str:
    body = str(text or "").strip()
    if not body:
        return f"{emoji} How was your recent visit with us?"
    if has_leading_emoji(body):
        return body
    return f"{emoji} {body}"


def extract_buttons_from_components(components: list[dict[str, Any]] | None) -> list[str]:
    labels: list[str] = []
    for comp in components or []:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("type") or "").upper() != "BUTTONS":
            continue
        for btn in comp.get("buttons") or []:
            if not isinstance(btn, dict):
                continue
            label = str(btn.get("text") or btn.get("title") or "").strip()
            if label:
                labels.append(label[:25])
    return labels


def default_buttons_for_key(template_key: str | None, *, name: str | None = None) -> list[str]:
    key = str(template_key or name or "").strip().lower()
    if any(token in key for token in ("thank", "done", "confirm_book", "booked")):
        return list(THANKS_BUTTONS)
    if any(token in key for token in ("recommend", "would_", "return_intent", "yes_no", "opt_in")):
        return list(YES_NO_BUTTONS)
    return list(RATING_BUTTONS)


def buttons_for_language(template_key: str | None, *, name: str | None, language: str | None) -> list[str]:
    key = str(template_key or name or "").strip().lower()
    if str(language or "").lower().startswith("ar"):
        if any(token in key for token in ("thank", "done", "confirm_book", "booked")):
            return list(AR_THANKS_BUTTONS)
        if any(token in key for token in ("recommend", "would_", "return_intent", "yes_no", "opt_in")):
            return list(AR_YES_NO_BUTTONS)
        return list(AR_RATING_BUTTONS)
    return default_buttons_for_key(template_key, name=name)


def utility_body_for_topic(topic_name: str | None, *, emoji: str = DEFAULT_EMOJI) -> str:
    topic = safe_topic_en(topic_name)
    return f"{emoji} How was {topic} for your recent visit with us? Reply with one option below."


def utility_body_ar_for_topic(topic_name: str | None, *, emoji: str = DEFAULT_EMOJI) -> str:
    topic = safe_topic_ar(topic_name)
    return f"{emoji} كيف كانت {topic} في زيارتك الأخيرة معنا؟ اختر أحد الخيارات أدناه."


def is_promo_wording(text: str | None) -> bool:
    s = str(text or "")
    return bool(PROMO_WORDS_EN.search(s) or PROMO_WORDS_AR.search(s))


def sanitize_utility_text(text: str | None, *, language: str | None = None) -> str:
    """Remove marketing words; return neutral Utility-safe text."""
    s = str(text or "").strip()
    if not s:
        if str(language or "").lower().startswith("ar"):
            return utility_body_ar_for_topic(None)
        return utility_body_for_topic(None)
    if not is_promo_wording(s):
        return ensure_leading_emoji(s)
    # Rebuild from topic-like fragment if possible.
    if str(language or "").lower().startswith("ar"):
        return utility_body_ar_for_topic(s)
    return utility_body_for_topic(s)


def build_utility_components(
    *,
    body: str,
    buttons: list[str],
    example_values: list[str] | None = None,
    language: str | None = None,
) -> list[dict[str, Any]]:
    body_text = sanitize_utility_text(body, language=language)
    vars_in_body = re.findall(r"\{\{(\d+)\}\}", body_text)
    examples = list(example_values or [])
    if vars_in_body and not examples:
        examples = ["your recent visit" for _ in vars_in_body]
    body_comp: dict[str, Any] = {"type": "BODY", "text": body_text}
    if examples:
        body_comp["example"] = {"body_text": [examples]}
    comps: list[dict[str, Any]] = [body_comp]
    labels = [str(b).strip()[:25] for b in buttons if str(b).strip()]
    labels = [re.sub(r"[^\w\s\-/'&]", "", b).strip()[:25] for b in labels]
    labels = [b for b in labels if b and not is_promo_wording(b)]
    if not labels:
        labels = list(AR_RATING_BUTTONS if str(language or "").lower().startswith("ar") else RATING_BUTTONS)
    comps.append(
        {
            "type": "BUTTONS",
            "buttons": [{"type": "QUICK_REPLY", "text": label} for label in labels[:3]],
        }
    )
    return comps


def components_have_buttons(components: list[dict[str, Any]] | None) -> bool:
    return bool(extract_buttons_from_components(components))


def parse_components_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def meta_name_has_promo(name: str | None) -> bool:
    return is_promo_wording(str(name or "").replace("_", " "))
