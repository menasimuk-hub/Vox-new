"""Knowledge base for Abuu WhatsApp agent — facts from DB only."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import AbuuAgentSettings, AbuuRestaurantSettings, Restaurant

GLOBAL_SETTINGS_ID = "global"

KB_TOPICS: tuple[str, ...] = (
    "hours",
    "delivery_hours",
    "delivery_zone",
    "prep_time",
    "minimum_order",
    "delivery_fee",
    "payment_methods",
    "refund",
    "cancellation",
    "allergens",
    "escalation",
    "holiday",
)

_KB_TOPIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "hours": (r"(?i)\b(hours|open|opening|close|closed)\b", r"ساعات", r"مواعيد", r"مفتوح", r"مغلق"),
    "delivery_hours": (r"(?i)\b(delivery hours|deliver until)\b", r"ساعات التوصيل", r"توصيل حتى"),
    "delivery_zone": (r"(?i)\b(delivery area|delivery zone|radius|deliver to)\b", r"منطقة التوصيل", r"نطاق"),
    "prep_time": (r"(?i)\b(prep|preparation|how long|ready in)\b", r"وقت التحضير", r"كم يستغرق"),
    "minimum_order": (r"(?i)\b(minimum order|min order)\b", r"حد أدنى", r"الحد الأدنى"),
    "delivery_fee": (r"(?i)\b(delivery fee|delivery charge|shipping)\b", r"رسوم التوصيل", r"تكلفة التوصيل"),
    "payment_methods": (r"(?i)\b(payment|pay|cash|card)\b", r"الدفع", r"كاش", r"بطاقة"),
    "refund": (r"(?i)\b(refund|money back)\b", r"استرداد", r"استرجاع"),
    "cancellation": (r"(?i)\b(cancel|cancellation)\b", r"إلغاء", r"الغاء"),
    "allergens": (r"(?i)\b(allerg|allergy|gluten|nuts)\b", r"حساسية", r"مسببات"),
    "escalation": (r"(?i)\b(manager|support|help me|complaint|angry)\b", r"مدير", r"دعم", r"شكوى"),
    "holiday": (r"(?i)\b(holiday|closed today|eid|ramadan)\b", r"عطلة", r"إجازة", r"عيد"),
}


@dataclass(frozen=True)
class ResolvedSettings:
    business_name_en: str | None
    business_name_ar: str | None
    opening_hours: dict[str, str]
    delivery_hours: dict[str, str]
    delivery_radius_km: float
    prep_minutes: int
    min_order_agorot: int
    delivery_fee_agorot: int
    payment_methods: list[str]
    refund_policy_en: str | None
    refund_policy_ar: str | None
    cancellation_policy_en: str | None
    cancellation_policy_ar: str | None
    allergen_disclaimer_en: str | None
    allergen_disclaimer_ar: str | None
    escalation_rules_en: str | None
    escalation_rules_ar: str | None
    greeting_template_en: str | None
    greeting_template_ar: str | None
    holiday_closures: list[dict[str, Any]]
    notes_en: str | None = None
    notes_ar: str | None = None
    restaurant_id: str | None = None


def _parse_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def get_global_settings(db: Session) -> AbuuAgentSettings:
    row = db.get(AbuuAgentSettings, GLOBAL_SETTINGS_ID)
    if row is None:
        from datetime import datetime

        row = AbuuAgentSettings(id=GLOBAL_SETTINGS_ID, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(row)
        db.flush()
    return row


def get_restaurant_settings(db: Session, restaurant_id: str) -> AbuuRestaurantSettings | None:
    return db.execute(
        select(AbuuRestaurantSettings).where(AbuuRestaurantSettings.restaurant_id == restaurant_id)
    ).scalar_one_or_none()


def resolve_settings(db: Session, *, restaurant_id: str | None = None) -> ResolvedSettings:
    global_row = get_global_settings(db)
    rest_row = get_restaurant_settings(db, restaurant_id) if restaurant_id else None
    restaurant = db.get(Restaurant, restaurant_id) if restaurant_id else None

    def pick(global_val, rest_val, fallback=None):
        if rest_val is not None:
            return rest_val
        if global_val is not None:
            return global_val
        return fallback

    radius = pick(global_row.default_delivery_radius_km, rest_row.delivery_radius_km if rest_row else None, 5.0)
    if restaurant and rest_row is None and restaurant.delivery_radius_km:
        radius = float(restaurant.delivery_radius_km)

    return ResolvedSettings(
        business_name_en=pick(global_row.business_name_en, None, "Abuu"),
        business_name_ar=pick(global_row.business_name_ar, None, "أبو"),
        opening_hours=_parse_json(pick(global_row.opening_hours_json, rest_row.opening_hours_json if rest_row else None), {}),
        delivery_hours=_parse_json(pick(global_row.delivery_hours_json, rest_row.delivery_hours_json if rest_row else None), {}),
        delivery_radius_km=float(radius or 5.0),
        prep_minutes=int(pick(global_row.default_prep_minutes, rest_row.prep_minutes if rest_row else None, 25) or 25),
        min_order_agorot=int(pick(global_row.default_min_order_agorot, rest_row.min_order_agorot if rest_row else None, 3500) or 3500),
        delivery_fee_agorot=int(pick(global_row.default_delivery_fee_agorot, rest_row.delivery_fee_agorot if rest_row else None, 1500) or 1500),
        payment_methods=_parse_json(pick(global_row.payment_methods_json, rest_row.payment_methods_json if rest_row else None), ["cash"]),
        refund_policy_en=pick(global_row.refund_policy_en, rest_row.refund_policy_en if rest_row else None),
        refund_policy_ar=pick(global_row.refund_policy_ar, rest_row.refund_policy_ar if rest_row else None),
        cancellation_policy_en=pick(global_row.cancellation_policy_en, rest_row.cancellation_policy_en if rest_row else None),
        cancellation_policy_ar=pick(global_row.cancellation_policy_ar, rest_row.cancellation_policy_ar if rest_row else None),
        allergen_disclaimer_en=pick(global_row.allergen_disclaimer_en, rest_row.allergen_disclaimer_en if rest_row else None),
        allergen_disclaimer_ar=pick(global_row.allergen_disclaimer_ar, rest_row.allergen_disclaimer_ar if rest_row else None),
        escalation_rules_en=pick(global_row.escalation_rules_en, rest_row.escalation_rules_en if rest_row else None),
        escalation_rules_ar=pick(global_row.escalation_rules_ar, rest_row.escalation_rules_ar if rest_row else None),
        greeting_template_en=pick(global_row.greeting_template_en, rest_row.greeting_template_en if rest_row else None),
        greeting_template_ar=pick(global_row.greeting_template_ar, rest_row.greeting_template_ar if rest_row else None),
        holiday_closures=_parse_json(pick(global_row.holiday_closures_json, rest_row.holiday_closures_json if rest_row else None), []),
        notes_en=rest_row.notes_en if rest_row else None,
        notes_ar=rest_row.notes_ar if rest_row else None,
        restaurant_id=restaurant_id,
    )


def detect_kb_topic(text: str) -> str | None:
    normalized = str(text or "").strip()
    if not normalized:
        return None
    for topic, patterns in _KB_TOPIC_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, normalized):
                return topic
    return None


def format_greeting(settings: ResolvedSettings, *, first_name: str | None, lang: str, saved_address: str | None = None) -> str:
    template = settings.greeting_template_en if lang == "en" else settings.greeting_template_ar
    name = first_name or ("there" if lang == "en" else "صديقي")
    if template:
        msg = template.replace("{name}", name)
    elif lang == "en":
        msg = f"Hello {name}, what would you like to eat today?"
    else:
        msg = f"مرحباً {name}، ماذا تحب أن تأكل اليوم؟"
    if lang == "en":
        msg += "\nTell me chicken, fish, meat, salad, drinks, chips, dessert, or vegetarian."
    else:
        msg += "\nاكتب: دجاج، سمك، لحم، سلطة، مشروبات، بطاطا، حلويات، أو نباتي."
    if saved_address:
        if lang == "en":
            msg += f"\nWe'll deliver to your saved address: {saved_address}"
        else:
            msg += f"\nسنوصل إلى عنوانك المحفوظ: {saved_address}"
    return msg


def answer_kb_question(settings: ResolvedSettings, topic: str, lang: str) -> str | None:
    topic = str(topic or "").strip().lower()
    if topic not in KB_TOPICS:
        return None

    def t(en_val: str | None, ar_val: str | None) -> str | None:
        return en_val if lang == "en" else (ar_val or en_val)

    if topic == "hours":
        hours = settings.opening_hours
        if not hours:
            return None
        lines = [f"{day}: {slot}" for day, slot in sorted(hours.items())]
        prefix = "Opening hours:\n" if lang == "en" else "ساعات العمل:\n"
        return prefix + "\n".join(lines)

    if topic == "delivery_hours":
        hours = settings.delivery_hours
        if not hours:
            return None
        lines = [f"{day}: {slot}" for day, slot in sorted(hours.items())]
        prefix = "Delivery hours:\n" if lang == "en" else "ساعات التوصيل:\n"
        return prefix + "\n".join(lines)

    if topic == "delivery_zone":
        km = settings.delivery_radius_km
        if lang == "en":
            return f"We deliver within {km:.1f} km of the restaurant."
        return f"نوصل ضمن {km:.1f} كم من المطعم."

    if topic == "prep_time":
        mins = settings.prep_minutes
        if lang == "en":
            return f"Average preparation time is about {mins} minutes."
        return f"متوسط وقت التحضير حوالي {mins} دقيقة."

    if topic == "minimum_order":
        amount = settings.min_order_agorot / 100
        if lang == "en":
            return f"Minimum order is {amount:.2f} ₪."
        return f"الحد الأدنى للطلب {amount:.2f} ₪."

    if topic == "delivery_fee":
        amount = settings.delivery_fee_agorot / 100
        if lang == "en":
            return f"Delivery fee is {amount:.2f} ₪."
        return f"رسوم التوصيل {amount:.2f} ₪."

    if topic == "payment_methods":
        methods = settings.payment_methods
        if not methods:
            return None
        joined = ", ".join(methods)
        if lang == "en":
            return f"Payment methods: {joined}."
        return f"طرق الدفع: {joined}."

    if topic == "refund":
        return t(settings.refund_policy_en, settings.refund_policy_ar)

    if topic == "cancellation":
        return t(settings.cancellation_policy_en, settings.cancellation_policy_ar)

    if topic == "allergens":
        return t(settings.allergen_disclaimer_en, settings.allergen_disclaimer_ar)

    if topic == "escalation":
        return t(settings.escalation_rules_en, settings.escalation_rules_ar)

    if topic == "holiday":
        if not settings.holiday_closures:
            if lang == "en":
                return "No holiday closures are scheduled right now."
            return "لا توجد إجازات مجدولة حالياً."
        lines = []
        for entry in settings.holiday_closures:
            reason = entry.get("reason_en" if lang == "en" else "reason_ar") or entry.get("reason_en") or entry.get("date")
            lines.append(f"{entry.get('date', '?')}: {reason}")
        prefix = "Holiday closures:\n" if lang == "en" else "إجازات:\n"
        return prefix + "\n".join(lines)

    return None


def kb_fallback_message(lang: str) -> str:
    if lang == "en":
        return "I don't have that information yet. Say **restaurants** to order or **abuu** to start."
    return "لا تتوفر هذه المعلومة بعد. اكتب **مطاعم** للطلب أو **abuu** للبدء."
