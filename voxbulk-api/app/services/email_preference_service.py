"""User email notification preferences (opt-in toggles for non-mandatory mail)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_email_preference import UserEmailPreference

# Toggleable categories shown in Settings → Profile.
EMAIL_PREF_CATALOG: list[dict[str, str]] = [
    {
        "key": "news_newsletter",
        "label": "News & newsletter",
        "description": "Product news, blog highlights, and marketing newsletters.",
    },
    {
        "key": "weekly_digest",
        "label": "Weekly digest",
        "description": "Weekly summary of activity across your organisation.",
    },
    {
        "key": "billing",
        "label": "Billing & invoices",
        "description": "Invoices, receipts, payment failures, plan and wallet updates.",
    },
    {
        "key": "usage_alerts",
        "label": "Usage alerts",
        "description": "Warnings when you approach or hit included usage limits.",
    },
    {
        "key": "surveys",
        "label": "Surveys",
        "description": "WhatsApp / AI survey campaign notifications for your team.",
    },
    {
        "key": "customer_feedback",
        "label": "Customer Feedback",
        "description": "Feedback location and follow-up related email alerts.",
    },
    {
        "key": "expo",
        "label": "Expo",
        "description": "Exhibition lead digests and visitor summary emails.",
    },
    {
        "key": "smart_card",
        "label": "Smart Card",
        "description": "Lead notifications, seat invites, and renewal reminders.",
    },
    {
        "key": "support",
        "label": "Support tickets",
        "description": "Updates when support tickets are created, replied to, or resolved.",
    },
    {
        "key": "team",
        "label": "Team & invites",
        "description": "Organisation invitations and team membership emails.",
    },
    {
        "key": "product_updates",
        "label": "Product updates",
        "description": "General product announcements and non-billing notifications.",
    },
]

EMAIL_PREF_KEYS: tuple[str, ...] = tuple(item["key"] for item in EMAIL_PREF_CATALOG)

# Template key → preference category. Missing / None = always send (security / account).
_TEMPLATE_PREF_MAP: dict[str, str | None] = {
    "forgot_password": None,
    "new_user": None,
    "account_deletion_completed": None,
    "demo_invite": None,
    "team_invite": "team",
    "weekly_digest": "weekly_digest",
    "general_notification": "product_updates",
    "usage_warning": "usage_alerts",
    "usage_warning_100": "usage_alerts",
    "new_invoice": "billing",
    "invoice_document": "billing",
    "payment_failed": "billing",
    "payment_receipt": "billing",
    "billing_cancellation": "billing",
    "billing_plan_change": "billing",
    "billing_wallet_credit": "billing",
    "billing_refund": "billing",
    "billing_renewal": "billing",
    "billing_pending_invoice": "billing",
    "billing_payment_action_required": "billing",
    "billing_subscription_ended": "billing",
    "sales_offer": "news_newsletter",
    "survey_ai_followup_promo": "surveys",
    "interview_scheduling_invite": None,
    "interview_booking_confirmed": None,
    "interview_booking_reminder": None,
    "interview_campaign_cancelled": None,
    "interview_meeting_missed": None,
    "interview_missed_call_followup": None,
    "interview_thank_you": None,
    "interview_session_reschedule": None,
    "interview_session_opted_out": None,
    "expo_visitor_catalogue": "expo",
    "expo_exhibitor_lead_digest": "expo",
    "expo_visitor_day_summary": "expo",
    "smart_card_lead_notify": "smart_card",
    "smart_card_rep_invite": "smart_card",
    "smart_card_rep_member_invite": "smart_card",
    "smart_card_renewal_reminder": "smart_card",
    "smart_card_renewal_reminder_7d": "smart_card",
    "smart_card_renewal_reminder_1d": "smart_card",
    "smart_card_expired": "smart_card",
    "support_ticket_created": "support",
    "support_ticket_reply": "support",
    "support_ticket_status": "support",
    "support_ticket_assigned": "support",
}

from app.data.brand_email_layout import EMAIL_PREFERENCES_MANAGE_URL

DASHBOARD_EMAIL_PREFS_URL = EMAIL_PREFERENCES_MANAGE_URL


def _default_prefs() -> dict[str, bool]:
    return {key: True for key in EMAIL_PREF_KEYS}


def _loads(raw: str | None) -> dict[str, bool]:
    base = _default_prefs()
    if not raw:
        return base
    try:
        data = json.loads(raw)
    except Exception:
        return base
    if not isinstance(data, dict):
        return base
    for key in EMAIL_PREF_KEYS:
        if key in data:
            base[key] = bool(data[key])
    return base


def _dumps(prefs: dict[str, bool]) -> str:
    clean = {key: bool(prefs.get(key, True)) for key in EMAIL_PREF_KEYS}
    return json.dumps(clean, separators=(",", ":"))


class EmailPreferenceService:
    @staticmethod
    def catalog() -> list[dict[str, str]]:
        return list(EMAIL_PREF_CATALOG)

    @staticmethod
    def get_prefs(db: Session, user_id: str) -> dict[str, bool]:
        row = db.get(UserEmailPreference, user_id)
        if row is None:
            return _default_prefs()
        return _loads(row.preferences_json)

    @staticmethod
    def get_for_user(db: Session, user_id: str) -> dict[str, Any]:
        prefs = EmailPreferenceService.get_prefs(db, user_id)
        return {
            "preferences": prefs,
            "categories": [
                {**item, "enabled": bool(prefs.get(item["key"], True))} for item in EMAIL_PREF_CATALOG
            ],
            "manage_url": DASHBOARD_EMAIL_PREFS_URL,
        }

    @staticmethod
    def update_prefs(db: Session, user_id: str, patch: dict[str, Any] | None) -> dict[str, Any]:
        current = EmailPreferenceService.get_prefs(db, user_id)
        incoming = patch if isinstance(patch, dict) else {}
        for key in EMAIL_PREF_KEYS:
            if key in incoming:
                current[key] = bool(incoming[key])
        row = db.get(UserEmailPreference, user_id)
        now = datetime.utcnow()
        if row is None:
            row = UserEmailPreference(user_id=user_id, preferences_json=_dumps(current), updated_at=now)
            db.add(row)
        else:
            row.preferences_json = _dumps(current)
            row.updated_at = now
            db.add(row)
        db.commit()
        return EmailPreferenceService.get_for_user(db, user_id)

    @staticmethod
    def pref_key_for_template(template_key: str) -> str | None:
        k = (template_key or "").strip().lower()
        if k in _TEMPLATE_PREF_MAP:
            return _TEMPLATE_PREF_MAP[k]
        if k.startswith("billing_"):
            return "billing"
        if k.startswith("interview_"):
            return None
        if k.startswith("smart_card_"):
            return "smart_card"
        if k.startswith("expo_"):
            return "expo"
        if k.startswith("support_"):
            return "support"
        if k.startswith("survey_"):
            return "surveys"
        if "newsletter" in k or k in {"news", "blog_news"}:
            return "news_newsletter"
        return "product_updates"

    @staticmethod
    def allows_template_for_email(db: Session, *, to_email: str, template_key: str) -> bool:
        pref_key = EmailPreferenceService.pref_key_for_template(template_key)
        if pref_key is None:
            return True
        email = (to_email or "").strip().lower()
        if not email:
            return True
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            return True
        prefs = EmailPreferenceService.get_prefs(db, user.id)
        return bool(prefs.get(pref_key, True))
