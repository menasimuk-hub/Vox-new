"""Seed Smart Card QR question templates, seat package, connection profile service, mailbox."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.plan import Plan
from app.models.plan_price import PlanPrice
from app.models.smart_card import (
    SMART_CARD_SERVICE_CODE,
    SmartCardPackage,
    SmartCardQuestionTemplate,
)
from app.models.smart_card_mailbox_settings import SMART_CARD_MAILBOX_ROW_ID, SmartCardMailboxSettings
from app.services.connection.constants import SERVICE_SMART_CARD
from app.services.smart_card.mailbox_settings_service import DEFAULT_FROM_NAME, DEFAULT_MAILBOX

# $5/seat/month billed yearly → $60/seat/year. PlanPrice yearly_price_minor is per seat.
# Admin can edit amounts later without overwrite when plan.is_frozen.
PACKAGE_SEED = {
    "code": "smart_card_seat",
    "name": "Smart Card QR — Seat",
    "order": 10,
    "featured": True,
    # yearly per-seat minor units
    "yearly_prices": {"USD": 6000, "GBP": 4800, "EUR": 5500, "CAD": 8000, "AUD": 9000},
    # monthly display hint (Admin UI)
    "monthly_prices": {"USD": 500, "GBP": 400, "EUR": 450, "CAD": 650, "AUD": 750},
    "features": [
        "1 representative seat (1 QR code)",
        "$5 per seat per month, billed annually",
        "WhatsApp + web questionnaire",
        "Business card OCR + AI lead scoring",
        "Catalogue / product PDF matching",
        "Representative login (own leads only)",
        "Owner/manager see all leads",
        "15 free preview tests before go-live",
    ],
}

QUESTION_TEMPLATES: list[dict] = [
    {
        "question_key": "contact",
        "label": "Contact",
        "prompt": "Please share your business card photo, or type your name.",
        "kind": "system",
        "sort_order": 10,
    },
    {
        "question_key": "interest",
        "label": "Interest",
        "prompt": "What are you most interested in today?",
        "kind": "selectable",
        "sort_order": 20,
        "description": "Open interest — used for product matching and lead scoring.",
    },
    {
        "question_key": "role",
        "label": "Role",
        "prompt": "What is your role / job title?",
        "kind": "selectable",
        "sort_order": 30,
    },
    {
        "question_key": "timeline",
        "label": "Timeline",
        "prompt": "When are you looking to move forward? (ASAP / this week / this month / later)",
        "kind": "selectable",
        "sort_order": 40,
    },
    {
        "question_key": "follow_up",
        "label": "Follow up",
        "prompt": "How should we follow up? (WhatsApp / Email / Call)",
        "kind": "selectable",
        "sort_order": 50,
    },
    {
        "question_key": "consent_info",
        "label": "Consent",
        "prompt": "Can we keep your details to send relevant information? (Yes / No)",
        "kind": "selectable",
        "sort_order": 60,
    },
    {
        "question_key": "open_feedback",
        "label": "Open feedback",
        "prompt": "Anything else we should know? (text or voice note)",
        "kind": "system",
        "sort_order": 70,
    },
    {
        "question_key": "thank_you",
        "label": "Thank you",
        "prompt": "Thank you — we have shared your details with the representative.",
        "kind": "system",
        "sort_order": 90,
    },
]


class SmartCardSeedService:
    @staticmethod
    def ensure_seeded(db: Session) -> None:
        SmartCardSeedService._ensure_mailbox(db)
        SmartCardSeedService._ensure_question_templates(db)
        SmartCardSeedService._ensure_packages(db)
        SmartCardSeedService._ensure_connection_profile_service(db)
        db.commit()

    @staticmethod
    def _ensure_mailbox(db: Session) -> None:
        row = db.execute(
            select(SmartCardMailboxSettings).where(SmartCardMailboxSettings.id == SMART_CARD_MAILBOX_ROW_ID)
        ).scalar_one_or_none()
        if row is None:
            db.add(
                SmartCardMailboxSettings(
                    id=SMART_CARD_MAILBOX_ROW_ID,
                    mailbox_email=DEFAULT_MAILBOX,
                    from_name=DEFAULT_FROM_NAME,
                    is_enabled=True,
                )
            )
            db.flush()

    @staticmethod
    def _ensure_question_templates(db: Session) -> None:
        now = datetime.utcnow()
        for item in QUESTION_TEMPLATES:
            key = str(item["question_key"])
            existing = db.execute(
                select(SmartCardQuestionTemplate).where(SmartCardQuestionTemplate.question_key == key)
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                SmartCardQuestionTemplate(
                    id=str(uuid.uuid4()),
                    question_key=key,
                    label=str(item["label"]),
                    prompt=str(item["prompt"]),
                    description=item.get("description"),
                    kind=str(item.get("kind") or "selectable"),
                    is_active=True,
                    sort_order=int(item.get("sort_order") or 100),
                    created_at=now,
                    updated_at=now,
                )
            )
        db.flush()

    @staticmethod
    def _ensure_packages(db: Session) -> None:
        now = datetime.utcnow()
        pkg = PACKAGE_SEED
        code = str(pkg["code"])
        features_json = json.dumps(pkg["features"])
        gbp_yearly = int(pkg["yearly_prices"]["GBP"])
        description = (
            "Smart Card QR — yearly seat subscription ($5/seat/month billed annually). "
            "Quantity = number of representative seats."
        )
        plan = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
        if plan is None:
            plan = Plan(
                id=str(uuid.uuid4()),
                code=code,
                name=pkg["name"],
                price_gbp_pence=gbp_yearly,
                interval="yearly",
                description=description,
                features_json=features_json,
                calls_included=0,
                whatsapp_included=0,
                service_kind=SMART_CARD_SERVICE_CODE,
                is_active=True,
                is_featured=bool(pkg.get("featured")),
                sort_order=int(pkg["order"]),
                created_at=now,
                updated_at=now,
            )
            db.add(plan)
            db.flush()
        elif not bool(getattr(plan, "is_frozen", False)):
            plan.name = pkg["name"]
            plan.service_kind = SMART_CARD_SERVICE_CODE
            plan.description = description
            plan.features_json = features_json
            plan.interval = "yearly"
            plan.is_active = True
            plan.is_featured = bool(pkg.get("featured"))
            plan.sort_order = int(pkg["order"])
            plan.updated_at = now
            db.add(plan)

        yearly = pkg["yearly_prices"]
        monthly = pkg["monthly_prices"]
        for currency, yearly_amount in yearly.items():
            price_row = db.execute(
                select(PlanPrice).where(PlanPrice.plan_id == plan.id, PlanPrice.currency == currency)
            ).scalar_one_or_none()
            if price_row is None:
                db.add(
                    PlanPrice(
                        id=str(uuid.uuid4()),
                        plan_id=plan.id,
                        currency=currency,
                        monthly_price_minor=int(monthly.get(currency) or 0),
                        yearly_price_minor=int(yearly_amount),
                        per_min_minor=0,
                        created_at=now,
                        updated_at=now,
                    )
                )
            elif not bool(getattr(plan, "is_frozen", False)):
                if price_row.yearly_price_minor is None:
                    price_row.yearly_price_minor = int(yearly_amount)
                if price_row.monthly_price_minor is None:
                    price_row.monthly_price_minor = int(monthly.get(currency) or 0)
                price_row.updated_at = now
                db.add(price_row)

        sc_pkg = db.execute(select(SmartCardPackage).where(SmartCardPackage.plan_id == plan.id)).scalar_one_or_none()
        if sc_pkg is None:
            db.add(
                SmartCardPackage(
                    id=str(uuid.uuid4()),
                    plan_id=plan.id,
                    tier="seat",
                    monthly_unit_hint_usd_cents=500,
                    display_order=int(pkg["order"]),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.flush()

    @staticmethod
    def _ensure_connection_profile_service(db: Session) -> None:
        from app.models.connection_profile import CHANNEL_WHATSAPP, ConnectionProfile, ConnectionProfileService

        profiles = db.execute(
            select(ConnectionProfile).where(ConnectionProfile.channel == CHANNEL_WHATSAPP)
        ).scalars().all()
        for profile in profiles:
            existing = db.execute(
                select(ConnectionProfileService).where(
                    ConnectionProfileService.profile_id == profile.id,
                    ConnectionProfileService.service_code == SERVICE_SMART_CARD,
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    ConnectionProfileService(
                        id=str(uuid.uuid4()),
                        profile_id=profile.id,
                        service_code=SERVICE_SMART_CARD,
                        enabled=True,
                    )
                )
        db.flush()
