"""CRUD for Abuu agent KB / policy settings."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.models.entities import AbuuAgentSettings, AbuuRestaurantSettings
from app.abuu.services.kb_service import GLOBAL_SETTINGS_ID, get_global_settings, get_restaurant_settings
from app.abuu.services.skill_definitions import default_skills_config


def _dump_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def agent_settings_to_dict(row: AbuuAgentSettings) -> dict[str, Any]:
    return {
        "id": row.id,
        "business_name_en": row.business_name_en,
        "business_name_ar": row.business_name_ar,
        "opening_hours": json.loads(row.opening_hours_json or "{}"),
        "delivery_hours": json.loads(row.delivery_hours_json or "{}"),
        "default_delivery_radius_km": row.default_delivery_radius_km,
        "default_prep_minutes": row.default_prep_minutes,
        "default_min_order_agorot": row.default_min_order_agorot,
        "default_delivery_fee_agorot": row.default_delivery_fee_agorot,
        "payment_methods": json.loads(row.payment_methods_json or "[]"),
        "refund_policy_en": row.refund_policy_en,
        "refund_policy_ar": row.refund_policy_ar,
        "cancellation_policy_en": row.cancellation_policy_en,
        "cancellation_policy_ar": row.cancellation_policy_ar,
        "allergen_disclaimer_en": row.allergen_disclaimer_en,
        "allergen_disclaimer_ar": row.allergen_disclaimer_ar,
        "escalation_rules_en": row.escalation_rules_en,
        "escalation_rules_ar": row.escalation_rules_ar,
        "greeting_template_en": row.greeting_template_en,
        "greeting_template_ar": row.greeting_template_ar,
        "holiday_closures": json.loads(row.holiday_closures_json or "[]"),
        "skills_config": json.loads(row.skills_config_json or "{}") or default_skills_config(),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def restaurant_settings_to_dict(row: AbuuRestaurantSettings) -> dict[str, Any]:
    return {
        "id": row.id,
        "restaurant_id": row.restaurant_id,
        "notes_en": row.notes_en,
        "notes_ar": row.notes_ar,
        "opening_hours": json.loads(row.opening_hours_json or "null") if row.opening_hours_json else None,
        "delivery_hours": json.loads(row.delivery_hours_json or "null") if row.delivery_hours_json else None,
        "delivery_radius_km": row.delivery_radius_km,
        "prep_minutes": row.prep_minutes,
        "min_order_agorot": row.min_order_agorot,
        "delivery_fee_agorot": row.delivery_fee_agorot,
        "payment_methods": json.loads(row.payment_methods_json or "null") if row.payment_methods_json else None,
        "refund_policy_en": row.refund_policy_en,
        "refund_policy_ar": row.refund_policy_ar,
        "cancellation_policy_en": row.cancellation_policy_en,
        "cancellation_policy_ar": row.cancellation_policy_ar,
        "allergen_disclaimer_en": row.allergen_disclaimer_en,
        "allergen_disclaimer_ar": row.allergen_disclaimer_ar,
        "escalation_rules_en": row.escalation_rules_en,
        "escalation_rules_ar": row.escalation_rules_ar,
        "greeting_template_en": row.greeting_template_en,
        "greeting_template_ar": row.greeting_template_ar,
        "holiday_closures": json.loads(row.holiday_closures_json or "null") if row.holiday_closures_json else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def patch_global_settings(db: Session, payload: dict[str, Any]) -> AbuuAgentSettings:
    row = get_global_settings(db)
    mapping = {
        "business_name_en": "business_name_en",
        "business_name_ar": "business_name_ar",
        "default_delivery_radius_km": "default_delivery_radius_km",
        "default_prep_minutes": "default_prep_minutes",
        "default_min_order_agorot": "default_min_order_agorot",
        "default_delivery_fee_agorot": "default_delivery_fee_agorot",
        "refund_policy_en": "refund_policy_en",
        "refund_policy_ar": "refund_policy_ar",
        "cancellation_policy_en": "cancellation_policy_en",
        "cancellation_policy_ar": "cancellation_policy_ar",
        "allergen_disclaimer_en": "allergen_disclaimer_en",
        "allergen_disclaimer_ar": "allergen_disclaimer_ar",
        "escalation_rules_en": "escalation_rules_en",
        "escalation_rules_ar": "escalation_rules_ar",
        "greeting_template_en": "greeting_template_en",
        "greeting_template_ar": "greeting_template_ar",
    }
    for key, attr in mapping.items():
        if key in payload:
            setattr(row, attr, payload[key])
    if "opening_hours" in payload:
        row.opening_hours_json = _dump_json(payload["opening_hours"])
    if "delivery_hours" in payload:
        row.delivery_hours_json = _dump_json(payload["delivery_hours"])
    if "payment_methods" in payload:
        row.payment_methods_json = _dump_json(payload["payment_methods"])
    if "holiday_closures" in payload:
        row.holiday_closures_json = _dump_json(payload["holiday_closures"])
    if "skills_config" in payload:
        row.skills_config_json = _dump_json(payload["skills_config"])
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.flush()
    return row


def patch_restaurant_settings(db: Session, restaurant_id: str, payload: dict[str, Any]) -> AbuuRestaurantSettings:
    row = get_restaurant_settings(db, restaurant_id)
    if row is None:
        row = AbuuRestaurantSettings(
            restaurant_id=restaurant_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
    for key in (
        "notes_en", "notes_ar", "delivery_radius_km", "prep_minutes",
        "min_order_agorot", "delivery_fee_agorot",
        "refund_policy_en", "refund_policy_ar",
        "cancellation_policy_en", "cancellation_policy_ar",
        "allergen_disclaimer_en", "allergen_disclaimer_ar",
        "escalation_rules_en", "escalation_rules_ar",
        "greeting_template_en", "greeting_template_ar",
    ):
        if key in payload:
            setattr(row, key, payload[key])
    if "opening_hours" in payload:
        row.opening_hours_json = _dump_json(payload["opening_hours"])
    if "delivery_hours" in payload:
        row.delivery_hours_json = _dump_json(payload["delivery_hours"])
    if "payment_methods" in payload:
        row.payment_methods_json = _dump_json(payload["payment_methods"])
    if "holiday_closures" in payload:
        row.holiday_closures_json = _dump_json(payload["holiday_closures"])
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.flush()
    return row


def get_skills_config(db: Session) -> dict[str, dict[str, bool]]:
    row = get_global_settings(db)
    raw = json.loads(row.skills_config_json or "{}")
    base = default_skills_config()
    if isinstance(raw, dict):
        for skill, cfg in raw.items():
            if skill in base and isinstance(cfg, dict):
                base[skill]["enabled"] = bool(cfg.get("enabled", True))
    return base


def is_skill_enabled(db: Session, skill: str) -> bool:
    cfg = get_skills_config(db)
    return bool(cfg.get(skill, {}).get("enabled", True))
