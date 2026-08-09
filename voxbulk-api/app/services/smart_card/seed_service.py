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
    SmartCardIndustry,
    SmartCardPackage,
    SmartCardQuestionTemplate,
)
from app.models.smart_card_mailbox_settings import SMART_CARD_MAILBOX_ROW_ID, SmartCardMailboxSettings
from app.services.connection.constants import SERVICE_SMART_CARD
from app.services.smart_card.mailbox_settings_service import DEFAULT_FROM_NAME, DEFAULT_MAILBOX

# $5/seat/month. Yearly = monthly × 12 × 0.8 (20% off). PlanPrice amounts are per seat.
# Admin can edit amounts later without overwrite when plan.is_frozen.
PACKAGE_SEED = {
    "code": "smart_card_seat",
    "name": "Smart Card QR — Seat",
    "order": 10,
    "featured": True,
    # yearly per-seat minor units (20% off annual)
    "yearly_prices": {"USD": 4800, "GBP": 3840, "EUR": 4320, "CAD": 6240, "AUD": 7200},
    # monthly per-seat minor units
    "monthly_prices": {"USD": 500, "GBP": 400, "EUR": 450, "CAD": 650, "AUD": 750},
    "features": [
        "1 representative seat (1 QR code)",
        "$5 per seat per month (or local equivalent)",
        "Pay yearly and save 20%",
        "WhatsApp + web questionnaire",
        "Business card OCR + AI lead scoring",
        "Catalogue / product PDF matching",
        "Representative login (own leads only)",
        "Owner/manager see all leads",
        "15 free preview tests before go-live",
    ],
}

INDUSTRY_SEEDS: list[dict] = [
    {
        "name": "Construction / Trade",
        "addon_question": "What size or type of projects are you currently working on?",
        "sort_order": 10,
    },
    {
        "name": "Retail / Wholesale",
        "addon_question": "Do you buy for one location, or multiple stores/branches?",
        "sort_order": 20,
    },
    {
        "name": "Tech / Solutions",
        "addon_question": "Do you have a rough budget range for this project?",
        "sort_order": 30,
    },
    {
        "name": "Food / Hospitality",
        "addon_question": "Are you sourcing for your business, or for events?",
        "sort_order": 40,
    },
    {
        "name": "Health / Wellness",
        "addon_question": "Are you buying for a clinic, practice, or retail setting?",
        "sort_order": 50,
    },
]

# Insert-missing only. Includes full Expo selectable bank + contact variants (Smart Card tables only).
QUESTION_TEMPLATES: list[dict] = [
    {
        "question_key": "contact",
        "label": "Contact (WhatsApp)",
        "prompt": "👋 Please send a photo of your business card, or type your name and company.",
        "kind": "system",
        "sort_order": 10,
        "description": "Business card or type details — default contact step.",
    },
    {
        "question_key": "contact_web",
        "label": "Contact (Web)",
        "prompt": "👋 Please upload a photo of your business card, or type your name and company.",
        "kind": "system",
        "sort_order": 11,
    },
    {
        "question_key": "contact_card_only",
        "label": "Contact card-only",
        "prompt": "📷 Please send a photo of your business card to continue.",
        "kind": "system",
        "sort_order": 12,
    },
    {
        "question_key": "contact_manual",
        "label": "Contact name (manual)",
        "prompt": "👤 What's your full name?",
        "kind": "system",
        "sort_order": 13,
    },
    {
        "question_key": "contact_company",
        "label": "Contact company",
        "prompt": "🏢 What's your company name?",
        "kind": "system",
        "sort_order": 14,
    },
    {
        "question_key": "contact_mobile",
        "label": "Contact mobile",
        "prompt": "📱 What's the best mobile number to reach you?",
        "kind": "system",
        "sort_order": 15,
    },
    {
        "question_key": "contact_confirm",
        "label": "Contact confirm",
        "prompt": "✅ Please check your details and continue.",
        "kind": "system",
        "sort_order": 16,
    },
    {
        "question_key": "interest",
        "label": "What they're looking for",
        "prompt": "🎯 What are you looking for today?",
        "kind": "selectable",
        "sort_order": 20,
        "description": "Open interest — used for product matching and lead scoring.",
    },
    {
        "question_key": "role",
        "label": "Role",
        "prompt": "👔 Which best describes your role?",
        "kind": "selectable",
        "sort_order": 30,
        "description": "Buyer / specifier / influencer — qualifies the lead.",
    },
    {
        "question_key": "timeline",
        "label": "Buying timeline",
        "prompt": "🗓️ When are you planning to decide or take the next step?",
        "kind": "selectable",
        "sort_order": 40,
        "description": "Used for Hot / Warm / Cold scoring.",
    },
    {
        "question_key": "follow_up",
        "label": "Follow-up preference",
        "prompt": "📞 How should we follow up? (you can pick more than one)",
        "kind": "selectable",
        "sort_order": 50,
        "description": "Preferred contact channel.",
    },
    {
        "question_key": "consent_info",
        "label": "Catalogue / price list",
        "prompt": "📋 Would you like our catalogue and/or price list? (Yes / No)",
        "kind": "selectable",
        "sort_order": 60,
        "description": "Yes/No catalogue interest (product pick uses Product request / Need catalogue).",
    },
    {
        "question_key": "marketing_consent",
        "label": "Contact consent (marketing)",
        "prompt": "📞 Can we keep your details to send relevant information? (Yes / No)",
        "kind": "selectable",
        "sort_order": 62,
        "description": "UK marketing / PECR-style opt-in — stores proof for your Lead results export.",
    },
    {
        "question_key": "offer_interest",
        "label": "Special offer",
        "prompt": "🎁 Are you interested in our special offer? (Yes / No)",
        "kind": "selectable",
        "sort_order": 65,
        "description": "Shown when you add an optional offer.",
    },
    {
        "question_key": "products_wanted",
        "label": "Product request",
        "prompt": "📦 Which product or brochure should we send you?",
        "kind": "selectable",
        "sort_order": 70,
        "description": "Visitor names a product — matched to your uploaded files.",
    },
    {
        "question_key": "budget",
        "label": "Budget",
        "prompt": "💷 Do you have a rough budget in mind for this?",
        "kind": "selectable",
        "sort_order": 75,
    },
    {
        "question_key": "volume",
        "label": "Volume / quantity",
        "prompt": "📊 Roughly what volume or quantity are you thinking about?",
        "kind": "selectable",
        "sort_order": 80,
    },
    {
        "question_key": "decision_maker",
        "label": "Decision-maker",
        "prompt": "✅ Are you the decision-maker for this, or recommending to someone else?",
        "kind": "selectable",
        "sort_order": 85,
    },
    {
        "question_key": "sourcing",
        "label": "Business or events",
        "prompt": "🏢 Are you sourcing for your business, or for events?",
        "kind": "selectable",
        "sort_order": 90,
    },
    {
        "question_key": "need_price_list",
        "label": "Need price list",
        "prompt": "💰 Would you like our latest price list?",
        "kind": "selectable",
        "sort_order": 95,
    },
    {
        "question_key": "need_catalogue",
        "label": "Need catalogue",
        "prompt": "📘 Would you like our product catalogue or brochure?",
        "kind": "selectable",
        "sort_order": 100,
    },
    {
        "question_key": "open_feedback",
        "label": "Anything else (voice/text)",
        "prompt": "📝 Please share anything else you'd like us to know.",
        "kind": "system",
        "sort_order": 110,
    },
    {
        "question_key": "thank_you",
        "label": "Thank you",
        "prompt": "✅ Thank you — we have shared your details with the representative.",
        "kind": "system",
        "sort_order": 120,
    },
    {
        "question_key": "company_card",
        "label": "Company card intro",
        "prompt": "Here are the contact details for your representative.",
        "kind": "system",
        "sort_order": 130,
    },
    {
        "question_key": "post_complete_handoff",
        "label": "Post-complete handoff",
        "prompt": "💬 You can reply here anytime if you have more questions.",
        "kind": "system",
        "sort_order": 140,
    },
]


class SmartCardSeedService:
    @staticmethod
    def ensure_seeded(db: Session) -> None:
        SmartCardSeedService._ensure_mailbox(db)
        SmartCardSeedService._ensure_industries(db)
        SmartCardSeedService._ensure_question_templates(db)
        SmartCardSeedService._ensure_packages(db)
        SmartCardSeedService._ensure_connection_profile_service(db)
        db.commit()

    @staticmethod
    def _ensure_industries(db: Session) -> None:
        now = datetime.utcnow()
        for item in INDUSTRY_SEEDS:
            name = str(item["name"]).strip()
            existing = db.execute(
                select(SmartCardIndustry).where(SmartCardIndustry.name == name)
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                SmartCardIndustry(
                    id=str(uuid.uuid4()),
                    name=name[:128],
                    addon_question=item.get("addon_question"),
                    is_active=True,
                    sort_order=int(item.get("sort_order") or 100),
                    created_at=now,
                    updated_at=now,
                )
            )
        db.flush()

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
        gbp_monthly = int(pkg["monthly_prices"]["GBP"])
        description = (
            "Smart Card QR — seat subscription ($5/seat/month, or pay yearly with 20% off). "
            "Quantity = number of representative seats."
        )
        plan = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
        if plan is None:
            plan = Plan(
                id=str(uuid.uuid4()),
                code=code,
                name=pkg["name"],
                price_gbp_pence=gbp_monthly,
                interval="monthly",
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
            plan.interval = "monthly"
            plan.price_gbp_pence = gbp_monthly
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
                # Upsert catalog list prices (20% yearly discount) unless Admin froze the plan.
                price_row.yearly_price_minor = int(yearly_amount)
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
