"""Code-written Utility WA template content: emoji + buttons + neutral wording (no marketing)."""

from __future__ import annotations

import json
import re
from typing import Any

DEFAULT_EMOJI = "📋"
STOP_FOOTER = "Reply STOP to opt out"
RATING_BUTTONS = ["Excellent", "Good", "Poor"]
YES_NO_BUTTONS = ["Yes", "No"]
THANKS_BUTTONS = ["Done"]
WELCOME_BUTTONS = ["Start survey"]
AR_RATING_BUTTONS = ["ممتاز", "جيد", "ضعيف"]
AR_YES_NO_BUTTONS = ["نعم", "لا"]
AR_THANKS_BUTTONS = ["تم"]
AR_WELCOME_BUTTONS = ["ابدأ الاستبيان"]

# Open-text system kinds: no quick-reply buttons.
NO_BUTTON_KINDS = frozenset({"thank_you", "tell_us_more", "final_feedback", "open_question"})

# Industry framing — never force "visit" on employee/internal surveys.
EMPLOYEE_INDUSTRY_SIGNALS = (
    "employee",
    "workplace",
    "staff_survey",
    "internal",
    "hr_",
)
CUSTOMER_VISIT_SIGNALS = (
    "hospitality",
    "restaurant",
    "retail",
    "clinic",
    "dental",
    "hotel",
    "salon",
    "cafe",
    "food",
)

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
    "would recommend": "overall satisfaction",
    "would_recommend": "overall satisfaction",
    "would recommend standard": "overall satisfaction",
    "would_recommend_standard": "overall satisfaction",
    "return intent": "future use",
    "return_intent": "future use",
    "return intent standard": "future use",
    "return_intent_standard": "future use",
    "repeat purchase intent": "shopping experience",
    "repeat_purchase_intent": "shopping experience",
    "repeat purchase": "shopping experience",
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


def _is_would_recommend_topic(topic_name: str | None) -> bool:
    key = _norm_topic_key(topic_name)
    return key in {"would recommend", "would recommend standard"} or key.startswith("would recommend")


def _is_repeat_purchase_topic(topic_name: str | None) -> bool:
    key = _norm_topic_key(topic_name)
    return key in {"repeat purchase intent", "repeat purchase"} or "repeat purchase" in key


_EMPLOYEE_TOPIC_BODIES: dict[str, str] = {
    "feeling valued": "How valued do you feel at work? Reply with one option below.",
    "recognition": "How would you rate the recognition you receive at work? Reply with one option below.",
    "remote hybrid flexibility": (
        "How satisfied are you with your remote/hybrid work flexibility? Reply with one option below."
    ),
    "inclusion belonging": (
        "At work, do you feel safe, welcome, and able to be your authentic self? Reply with one option below."
    ),
    "manager communication": (
        "At work, does your manager share information, feedback, and expectations clearly? "
        "Reply with one option below."
    ),
    "morale": "How would you rate morale at work at the moment? Reply with one option below.",
    "motivation": (
        "How energized and driven do you feel to perform well in your role? Reply with one option below."
    ),
    "psychological safety": (
        "At work, do you feel able to speak up about concerns or suggestions without fear of "
        "negative consequences? Reply with one option below."
    ),
}


def employee_utility_body_for_topic(topic_name: str | None) -> str | None:
    key = _norm_topic_key(topic_name)
    return _EMPLOYEE_TOPIC_BODIES.get(key)


def _has_latin(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]", text or ""))


def resolve_industry_frame(
    industry_slug: str | None = None,
    industry_name: str | None = None,
    *,
    language: str | None = None,
) -> dict[str, str]:
    """Return framing phrases for Utility survey copy (EN or AR)."""
    blob = f"{industry_slug or ''} {industry_name or ''}".strip().lower().replace("-", "_")
    ar = str(language or "").lower().startswith("ar")
    if any(sig in blob for sig in EMPLOYEE_INDUSTRY_SIGNALS):
        if ar:
            return {
                "key": "employee",
                "context": "في عملك",
                "experience": "تجربتك في العمل",
                "fallback_topic": "عملك",
            }
        return {
            "key": "employee",
            "context": "at work",
            "experience": "your experience at work",
            "fallback_topic": "your work",
        }
    if any(sig in blob for sig in CUSTOMER_VISIT_SIGNALS):
        if ar:
            return {
                "key": "visit",
                "context": "في زيارتك الأخيرة معنا",
                "experience": "زيارتك الأخيرة معنا",
                "fallback_topic": "هذه الخدمة",
            }
        return {
            "key": "visit",
            "context": "on your recent visit with us",
            "experience": "your recent visit with us",
            "fallback_topic": "your recent visit",
        }
    if ar:
        return {
            "key": "experience",
            "context": "في تجربتك الأخيرة معنا",
            "experience": "تجربتك الأخيرة معنا",
            "fallback_topic": "هذه الخدمة",
        }
    return {
        "key": "experience",
        "context": "in your recent experience with us",
        "experience": "your recent experience with us",
        "fallback_topic": "your recent experience",
    }


def safe_topic_en(
    topic_name: str | None,
    *,
    industry_slug: str | None = None,
    industry_name: str | None = None,
) -> str:
    frame = resolve_industry_frame(industry_slug, industry_name, language="en")
    raw = str(topic_name or "").strip()
    key = _norm_topic_key(raw)
    if key in TOPIC_SAFE_EN:
        return TOPIC_SAFE_EN[key]
    slug_key = key.replace(" ", "_")
    if slug_key in TOPIC_SAFE_EN:
        return TOPIC_SAFE_EN[slug_key]
    # Strip banned words from topic label.
    cleaned = PROMO_WORDS_EN.sub("service", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip() or frame["fallback_topic"]
    if is_promo_wording(cleaned):
        return frame["fallback_topic"]
    return cleaned.lower()


def safe_topic_ar(
    topic_name: str | None,
    *,
    industry_slug: str | None = None,
    industry_name: str | None = None,
) -> str:
    frame = resolve_industry_frame(industry_slug, industry_name, language="ar")
    raw = str(topic_name or "").strip()
    key = _norm_topic_key(raw)
    if key in TOPIC_SAFE_AR:
        return TOPIC_SAFE_AR[key]
    slug_key = key.replace(" ", "_")
    if slug_key in TOPIC_SAFE_AR:
        return TOPIC_SAFE_AR[slug_key]
    # Never inject English into Arabic bodies.
    if _has_latin(raw) or is_promo_wording(raw):
        return frame["fallback_topic"]
    cleaned = PROMO_WORDS_AR.sub("", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or frame["fallback_topic"]


def has_leading_emoji(text: str | None) -> bool:
    body = str(text or "").strip()
    if not body:
        return False
    ch = body[0]
    return ord(ch) > 127 or ch in {"✅", "📋", "⭐", "🙏", "💬", "📝", "👍", "👋", "🔔"}


def ensure_leading_emoji(
    text: str | None,
    *,
    emoji: str = DEFAULT_EMOJI,
    industry_slug: str | None = None,
    industry_name: str | None = None,
    language: str | None = None,
) -> str:
    body = str(text or "").strip()
    if not body:
        frame = resolve_industry_frame(industry_slug, industry_name, language=language)
        if str(language or "").lower().startswith("ar"):
            return f"{emoji} كيف كانت {frame['experience']}؟"
        return f"{emoji} How was {frame['experience']}?"
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


def _kind_from_key_or_name(template_key: str | None, name: str | None = None) -> str:
    key = str(template_key or name or "").strip().lower()
    for kind in ("welcome", "thank_you", "tell_us_more", "final_feedback", "open_question"):
        if kind in key:
            return kind
    return ""


def default_buttons_for_key(
    template_key: str | None,
    *,
    name: str | None = None,
    system_kind: str | None = None,
) -> list[str]:
    kind = str(system_kind or _kind_from_key_or_name(template_key, name)).strip().lower()
    if kind == "welcome" or (not kind and "welcome" in str(template_key or name or "").lower()):
        return list(WELCOME_BUTTONS)
    if kind in NO_BUTTON_KINDS or any(
        token in str(template_key or name or "").lower()
        for token in ("thank_you", "tell_us_more", "final_feedback", "open_question")
    ):
        return []
    if any(token in str(template_key or name or "").lower() for token in ("yes_no", "opt_in", "return_intent")):
        return list(YES_NO_BUTTONS)
    return list(RATING_BUTTONS)


def buttons_for_language(
    template_key: str | None,
    *,
    name: str | None,
    language: str | None,
    system_kind: str | None = None,
) -> list[str]:
    kind = str(system_kind or _kind_from_key_or_name(template_key, name)).strip().lower()
    ar = str(language or "").lower().startswith("ar")
    if kind == "welcome" or (not kind and "welcome" in str(template_key or name or "").lower()):
        return list(AR_WELCOME_BUTTONS if ar else WELCOME_BUTTONS)
    if kind in NO_BUTTON_KINDS or any(
        token in str(template_key or name or "").lower()
        for token in ("thank_you", "tell_us_more", "final_feedback", "open_question")
    ):
        return []
    if ar:
        if any(token in str(template_key or name or "").lower() for token in ("yes_no", "opt_in", "return_intent")):
            return list(AR_YES_NO_BUTTONS)
        return list(AR_RATING_BUTTONS)
    return default_buttons_for_key(template_key, name=name, system_kind=system_kind)


def utility_body_for_topic(
    topic_name: str | None,
    *,
    emoji: str = DEFAULT_EMOJI,
    industry_slug: str | None = None,
    industry_name: str | None = None,
) -> str:
    frame = resolve_industry_frame(industry_slug, industry_name, language="en")
    prefix = f"{emoji} " if emoji else ""

    if _is_would_recommend_topic(topic_name):
        if frame["key"] == "visit":
            return (
                f"{prefix}How would you rate your overall satisfaction on your recent visit? "
                "Reply with one option below."
            ).strip()
        return (
            f"{prefix}How would you rate your overall satisfaction from your recent experience with us? "
            "Reply with one option below."
        ).strip()

    if _is_repeat_purchase_topic(topic_name):
        return (
            f"{prefix}After your recent visit with us, how satisfied are you with your shopping experience? "
            "Reply with one option below."
        ).strip()

    topic = safe_topic_en(topic_name, industry_slug=industry_slug, industry_name=industry_name)
    employee_body = employee_utility_body_for_topic(topic_name) or employee_utility_body_for_topic(topic)
    if frame["key"] == "employee":
        if employee_body:
            return f"{prefix}{employee_body}".strip()
        return f"{prefix}How would you rate {topic} at work? Reply with one option below.".strip()
    if frame["key"] == "visit":
        return f"{prefix}How would you rate your {topic} on your recent visit? Reply with one option below.".strip()
    return (
        f"{prefix}How would you rate your {topic} from your recent experience with us? "
        "Reply with one option below."
    ).strip()


def utility_body_ar_for_topic(
    topic_name: str | None,
    *,
    emoji: str = DEFAULT_EMOJI,
    industry_slug: str | None = None,
    industry_name: str | None = None,
) -> str:
    frame = resolve_industry_frame(industry_slug, industry_name, language="ar")
    topic = safe_topic_ar(topic_name, industry_slug=industry_slug, industry_name=industry_name)
    if frame["key"] == "employee":
        return f"{emoji} كيف تقيّم {topic} في عملك؟ اختر أحد الخيارات أدناه."
    if frame["key"] == "visit":
        return f"{emoji} كيف كانت {topic} في زيارتك الأخيرة معنا؟ اختر أحد الخيارات أدناه."
    return f"{emoji} كيف كانت {topic} في تجربتك الأخيرة معنا؟ اختر أحد الخيارات أدناه."


def is_promo_wording(text: str | None) -> bool:
    s = str(text or "")
    return bool(PROMO_WORDS_EN.search(s) or PROMO_WORDS_AR.search(s))


def sanitize_utility_text(
    text: str | None,
    *,
    language: str | None = None,
    industry_slug: str | None = None,
    industry_name: str | None = None,
) -> str:
    """Remove marketing words; return neutral Utility-safe text."""
    s = str(text or "").strip()
    if not s:
        if str(language or "").lower().startswith("ar"):
            return utility_body_ar_for_topic(
                None, industry_slug=industry_slug, industry_name=industry_name
            )
        return utility_body_for_topic(
            None, industry_slug=industry_slug, industry_name=industry_name
        )
    if not is_promo_wording(s):
        return ensure_leading_emoji(
            s,
            industry_slug=industry_slug,
            industry_name=industry_name,
            language=language,
        )
    if str(language or "").lower().startswith("ar"):
        return utility_body_ar_for_topic(
            s, industry_slug=industry_slug, industry_name=industry_name
        )
    return utility_body_for_topic(
        s, industry_slug=industry_slug, industry_name=industry_name
    )


def build_utility_components(
    *,
    body: str,
    buttons: list[str],
    example_values: list[str] | None = None,
    language: str | None = None,
    industry_slug: str | None = None,
    industry_name: str | None = None,
    allow_empty_buttons: bool = False,
) -> list[dict[str, Any]]:
    body_text = sanitize_utility_text(
        body,
        language=language,
        industry_slug=industry_slug,
        industry_name=industry_name,
    )
    vars_in_body = re.findall(r"\{\{(\d+)\}\}", body_text)
    examples = list(example_values or [])
    if vars_in_body and not examples:
        frame = resolve_industry_frame(industry_slug, industry_name, language=language)
        examples = [frame["fallback_topic"] for _ in vars_in_body]
    body_comp: dict[str, Any] = {"type": "BODY", "text": body_text}
    if examples:
        body_comp["example"] = {"body_text": [examples]}
    comps: list[dict[str, Any]] = [body_comp]
    # Every WhatsApp template must include the opt-out footer.
    comps.append({"type": "FOOTER", "text": STOP_FOOTER})
    labels = [str(b).strip()[:25] for b in buttons if str(b).strip()]
    labels = [re.sub(r"[^\w\s\-/'&]", "", b).strip()[:25] for b in labels]
    labels = [b for b in labels if b and not is_promo_wording(b)]
    if not labels and not allow_empty_buttons:
        labels = list(AR_RATING_BUTTONS if str(language or "").lower().startswith("ar") else RATING_BUTTONS)
    if labels:
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
