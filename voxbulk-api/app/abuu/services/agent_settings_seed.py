"""Seed demo KB / agent settings for Abuu."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.abuu.models.entities import AbuuAgentSettings, AbuuRestaurantSettings
from app.abuu.services.kb_service import GLOBAL_SETTINGS_ID
from app.abuu.services.skill_definitions import default_skills_config

_DEFAULT_HOURS = {
    "mon": "10:00-23:00",
    "tue": "10:00-23:00",
    "wed": "10:00-23:00",
    "thu": "10:00-23:00",
    "fri": "10:00-23:00",
    "sat": "10:00-23:00",
    "sun": "10:00-23:00",
}

_DELIVERY_HOURS = {
    "mon": "11:00-22:30",
    "tue": "11:00-22:30",
    "wed": "11:00-22:30",
    "thu": "11:00-22:30",
    "fri": "11:00-22:30",
    "sat": "11:00-22:30",
    "sun": "11:00-22:30",
}


def seed_agent_settings(db: Session) -> dict:
    now = datetime.utcnow()
    row = db.get(AbuuAgentSettings, GLOBAL_SETTINGS_ID)
    if row is None:
        row = AbuuAgentSettings(id=GLOBAL_SETTINGS_ID, created_at=now, updated_at=now)
        db.add(row)

    row.business_name_en = row.business_name_en or "Abuu Gaza"
    row.business_name_ar = row.business_name_ar or "أبو غزة"
    row.opening_hours_json = row.opening_hours_json or json.dumps(_DEFAULT_HOURS)
    row.delivery_hours_json = row.delivery_hours_json or json.dumps(_DELIVERY_HOURS)
    row.default_delivery_radius_km = row.default_delivery_radius_km or 5.0
    row.default_prep_minutes = row.default_prep_minutes or 25
    row.default_min_order_agorot = row.default_min_order_agorot or 3500
    row.default_delivery_fee_agorot = row.default_delivery_fee_agorot or 1500
    row.payment_methods_json = row.payment_methods_json or json.dumps(["cash", "card_on_delivery"])
    row.refund_policy_en = row.refund_policy_en or "Refunds are reviewed within 24 hours for undelivered or incorrect orders."
    row.refund_policy_ar = row.refund_policy_ar or "يتم مراجعة الاسترداد خلال 24 ساعة للطلبات غير المسلمة أو الخاطئة."
    row.cancellation_policy_en = row.cancellation_policy_en or "You may cancel before the restaurant starts preparing your order."
    row.cancellation_policy_ar = row.cancellation_policy_ar or "يمكنك الإلغاء قبل أن يبدأ المطعم بتجهيز طلبك."
    row.allergen_disclaimer_en = row.allergen_disclaimer_en or "Please tell us about allergies when ordering. Cross-contact may occur in kitchens."
    row.allergen_disclaimer_ar = row.allergen_disclaimer_ar or "يرجى إخبارنا بالحساسية عند الطلب. قد يحدث تلامس في المطبخ."
    row.escalation_rules_en = row.escalation_rules_en or "For urgent issues, reply HELP and our team will contact you on WhatsApp."
    row.escalation_rules_ar = row.escalation_rules_ar or "للمشاكل العاجلة، أرسل «مساعدة» وسيتواصل فريقنا معك على واتساب."
    row.greeting_template_en = row.greeting_template_en or "Hey {name}! 😊 What are you craving today?"
    row.greeting_template_ar = row.greeting_template_ar or (
        "أهلاً {name}! 😊 شو جوعان اليوم؟\n\n"
        "📝 للطلب بالأرقام: أطباق 1 2 3 • كمية 1*3 • من جديد yallasay • مساعدة: مساعدة"
    )
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    row.holiday_closures_json = row.holiday_closures_json or json.dumps(
        [{"date": tomorrow, "reason_en": "Demo closure", "reason_ar": "إغلاق تجريبي"}]
    )
    row.skills_config_json = row.skills_config_json or json.dumps(default_skills_config())
    row.updated_at = now
    db.add(row)

    overrides = [
        {
            "restaurant_id": "abuu-rest-chicken",
            "prep_minutes": 20,
            "min_order_agorot": 3000,
            "notes_en": "Best for grilled chicken and shawarma.",
            "notes_ar": "الأفضل للدجاج المشوي والشاورما.",
        },
        {
            "restaurant_id": "abuu-rest-fish",
            "delivery_fee_agorot": 2000,
            "allergen_disclaimer_en": "Contains fish and shellfish. Not suitable for fish allergy.",
            "allergen_disclaimer_ar": "يحتوي على أسماك ومأكولات بحرية.",
        },
    ]
    created = 0
    for spec in overrides:
        existing = db.execute(
            __import__("sqlalchemy").select(AbuuRestaurantSettings).where(
                AbuuRestaurantSettings.restaurant_id == spec["restaurant_id"]
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = AbuuRestaurantSettings(
                restaurant_id=spec["restaurant_id"],
                created_at=now,
                updated_at=now,
            )
            db.add(existing)
            created += 1
        for key, value in spec.items():
            if key != "restaurant_id" and hasattr(existing, key):
                if getattr(existing, key) is None:
                    setattr(existing, key, value)
        existing.updated_at = now
        db.add(existing)

    db.flush()
    return {"global": 1, "restaurant_overrides": created}


def refresh_pilot_allergen_disclaimers(db: Session) -> int:
    """Ensure fish/chicken pilot restaurants have kitchen allergen disclaimers."""
    now = datetime.utcnow()
    seed_agent_settings(db)
    specs = [
        {
            "restaurant_id": "abuu-rest-fish",
            "allergen_disclaimer_en": "Contains fish and shellfish. Not suitable for fish allergy.",
            "allergen_disclaimer_ar": "يحتوي على أسماك ومأكولات بحرية. غير مناسب لمن لديه حساسية من السمك.",
        },
        {
            "restaurant_id": "abuu-rest-chicken",
            "allergen_disclaimer_en": "May contain dairy, gluten, and nuts. Tell us your allergies when ordering.",
            "allergen_disclaimer_ar": "قد يحتوي على ألبان وجلوتين ومكسرات. أخبرنا عن حساسيتك عند الطلب.",
        },
        {
            "restaurant_id": "abuu-rest-meat",
            "allergen_disclaimer_en": "Grilled meat dishes. Tell us about allergies when ordering.",
            "allergen_disclaimer_ar": "أطباق لحوم مشوية. أخبرنا عن الحساسية عند الطلب.",
        },
        {
            "restaurant_id": "abuu-rest-vegetarian",
            "allergen_disclaimer_en": "Plant-based menu. May contain nuts and sesame.",
            "allergen_disclaimer_ar": "قائمة نباتية. قد تحتوي على مكسرات وسمسم.",
        },
    ]
    updated = 0
    for spec in specs:
        row = db.execute(
            __import__("sqlalchemy").select(AbuuRestaurantSettings).where(
                AbuuRestaurantSettings.restaurant_id == spec["restaurant_id"]
            )
        ).scalar_one_or_none()
        if row is None:
            row = AbuuRestaurantSettings(
                restaurant_id=spec["restaurant_id"],
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        row.allergen_disclaimer_en = spec["allergen_disclaimer_en"]
        row.allergen_disclaimer_ar = spec["allergen_disclaimer_ar"]
        row.updated_at = now
        db.add(row)
        updated += 1
    db.flush()
    return updated
