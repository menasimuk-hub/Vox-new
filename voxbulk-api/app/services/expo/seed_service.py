"""Seed Expo industries and 1 / 3 / 7 day duration packages (multi-currency)."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.expo import EXPO_SERVICE_CODE, ExpoBooth, ExpoIndustry, ExpoPackage, ExpoQuestionTemplate
from app.models.plan import Plan
from app.models.plan_price import PlanPrice

INDUSTRY_SEEDS: list[dict] = [
    {
        "slug": "construction",
        "name": "Construction / Trade",
        "addon_question": "What size or type of projects are you currently working on?",
    },
    {
        "slug": "retail",
        "name": "Retail / Wholesale",
        "addon_question": "Do you buy for one location, or multiple stores/branches?",
    },
    {
        "slug": "tech",
        "name": "Tech / Solutions",
        "addon_question": "Do you have a rough budget range for this project?",
    },
    {
        "slug": "food",
        "name": "Food / Hospitality",
        "addon_question": "Are you sourcing for your business, or for events?",
    },
    {
        "slug": "finance",
        "name": "Finance / Business services",
        "addon_question": "Are you looking to start this in the next few weeks or months?",
    },
    {
        "slug": "logistics",
        "name": "Logistics / Supply chain",
        "addon_question": "What routes or volumes are you looking to cover?",
    },
    {
        "slug": "health",
        "name": "Health / Wellness",
        "addon_question": "Are you buying for a clinic, practice, or retail setting?",
    },
    {
        "slug": "franchise",
        "name": "Franchising / Startups",
        "addon_question": "Are you exploring a franchise, partnership, or first-time launch?",
    },
]

UNIVERSAL_QUESTIONS: list[dict] = [
    {"key": "name", "prompt": "Hi! Thanks for stopping by our stand today — what's your name?"},
    {"key": "company", "prompt": "Which company or organisation do you represent?"},
    {"key": "interest", "prompt": "What is the main thing you're looking for or interested in right now?"},
    {"key": "timeline", "prompt": "When are you planning to make a decision or take action on this?"},
    {
        "key": "consent_info",
        "prompt": "Would you like us to send you our latest information and special offers? (Yes / No)",
    },
]

# Canonical duration packages — one plan per tier, prices per currency on PlanPrice.
PACKAGE_TIERS: list[dict] = [
    {
        "tier": "day1",
        "code": "expo_day1",
        "name": "Expo 1 Day",
        "duration_days": 1,
        "order": 10,
        "featured": False,
        "max_booths": 1,
        "max_assets": 5,
        "lead_scoring": True,
        "post_show_followup": False,
        "post_event_survey": False,
        "ai_summary": False,
        "prices": {"GBP": 4900, "EUR": 5900, "USD": 6500, "CAD": 8900, "AUD": 9900},
        "features": [
            "Booth active for 1 day",
            "Unique QR code per exhibitor",
            "WhatsApp qualifying questions",
            "Optional product / brochure delivery",
            "Hot / Warm / Cold lead scoring",
            "Full structured lead export (CSV)",
            "GDPR / international privacy compliance",
        ],
    },
    {
        "tier": "day3",
        "code": "expo_day3",
        "name": "Expo 3 Days",
        "duration_days": 3,
        "order": 20,
        "featured": True,
        "max_booths": 1,
        "max_assets": 5,
        "lead_scoring": True,
        "post_show_followup": False,
        "post_event_survey": False,
        "ai_summary": False,
        "prices": {"GBP": 9900, "EUR": 11900, "USD": 12900, "CAD": 16900, "AUD": 18900},
        "features": [
            "Booth active for 3 days",
            "Unique QR code per exhibitor",
            "WhatsApp qualifying questions",
            "Optional product / brochure delivery",
            "Hot / Warm / Cold lead scoring",
            "Full structured lead export (CSV)",
            "GDPR / international privacy compliance",
        ],
    },
    {
        "tier": "day7",
        "code": "expo_day7",
        "name": "Expo 7 Days",
        "duration_days": 7,
        "order": 30,
        "featured": False,
        "max_booths": 1,
        "max_assets": 5,
        "lead_scoring": True,
        "post_show_followup": False,
        "post_event_survey": False,
        "ai_summary": False,
        "prices": {"GBP": 14900, "EUR": 17900, "USD": 19900, "CAD": 24900, "AUD": 27900},
        "features": [
            "Booth active for 7 days",
            "Unique QR code per exhibitor",
            "WhatsApp qualifying questions",
            "Optional product / brochure delivery",
            "Hot / Warm / Cold lead scoring",
            "Full structured lead export (CSV)",
            "GDPR / international privacy compliance",
        ],
    },
]

CANONICAL_EXPO_CODES = {str(t["code"]) for t in PACKAGE_TIERS}


class ExpoSeedService:
    @staticmethod
    def ensure_seeded(db: Session) -> None:
        ExpoSeedService._ensure_industries(db)
        ExpoSeedService._ensure_question_templates(db)
        ExpoSeedService._upgrade_legacy_booth_questions(db)
        ExpoSeedService._ensure_packages(db)
        ExpoSeedService._ensure_connection_profile_expo_service(db)
        db.commit()

    @staticmethod
    def _ensure_question_templates(db: Session) -> None:
        from app.services.expo.question_bank import SELECTABLE_QUESTION_BANK

        now = datetime.utcnow()
        for idx, q in enumerate(SELECTABLE_QUESTION_BANK):
            key = str(q["key"])
            row = db.execute(
                select(ExpoQuestionTemplate).where(ExpoQuestionTemplate.question_key == key)
            ).scalar_one_or_none()
            if row is None:
                db.add(
                    ExpoQuestionTemplate(
                        id=str(uuid.uuid4()),
                        question_key=key,
                        label=str(q.get("label") or key)[:128],
                        prompt=str(q.get("prompt") or "")[:4000],
                        description=str(q.get("description") or "")[:2000] or None,
                        matches_products=bool(q.get("matches_products")),
                        is_active=True,
                        sort_order=(idx + 1) * 10,
                        created_at=now,
                        updated_at=now,
                    )
                )
            # Existing Admin-edited rows are never overwritten (insert-missing only).
        db.flush()

    @staticmethod
    def _upgrade_legacy_booth_questions(db: Session) -> None:
        """Rewrite booths still using price-list/catalogue Yes/No defaults to the smart lead set."""
        from app.services.expo.question_bank import upgrade_booth_question_config

        now = datetime.utcnow()
        booths = db.execute(select(ExpoBooth)).scalars().all()
        for booth in booths:
            upgraded = upgrade_booth_question_config(booth.question_config_json)
            if not upgraded:
                continue
            booth.question_config_json = upgraded
            booth.updated_at = now
            db.add(booth)
        db.flush()

    @staticmethod
    def _ensure_connection_profile_expo_service(db: Session) -> None:
        """Existing WA profiles pre-date SERVICE_EXPO — add enabled expo rows so outbound resolves."""
        from app.models.connection_profile import CHANNEL_WHATSAPP, ConnectionProfile, ConnectionProfileService
        from app.services.connection.constants import SERVICE_EXPO

        now = datetime.utcnow()
        profiles = db.execute(
            select(ConnectionProfile).where(
                ConnectionProfile.channel == CHANNEL_WHATSAPP,
                ConnectionProfile.is_active.is_(True),
            )
        ).scalars().all()
        for profile in profiles:
            row = db.execute(
                select(ConnectionProfileService).where(
                    ConnectionProfileService.profile_id == profile.id,
                    ConnectionProfileService.service_code == SERVICE_EXPO,
                )
            ).scalar_one_or_none()
            if row is None:
                db.add(
                    ConnectionProfileService(
                        id=str(uuid.uuid4()),
                        profile_id=profile.id,
                        service_code=SERVICE_EXPO,
                        enabled=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
            elif not bool(row.enabled):
                row.enabled = True
                row.updated_at = now
                db.add(row)
        db.flush()

    @staticmethod
    def _ensure_industries(db: Session) -> None:
        now = datetime.utcnow()
        for idx, ind in enumerate(INDUSTRY_SEEDS):
            row = db.execute(select(ExpoIndustry).where(ExpoIndustry.slug == ind["slug"])).scalar_one_or_none()
            if row is None:
                db.add(
                    ExpoIndustry(
                        id=str(uuid.uuid4()),
                        slug=ind["slug"],
                        name=ind["name"],
                        addon_question=ind.get("addon_question"),
                        sort_order=(idx + 1) * 10,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.name = ind["name"]
                row.addon_question = ind.get("addon_question")
                row.is_active = True
                row.updated_at = now
                db.add(row)
        db.flush()

    @staticmethod
    def _tier_from_plan_code(code: str) -> str | None:
        raw = str(code or "").strip().lower()
        if raw in CANONICAL_EXPO_CODES:
            return raw.replace("expo_", "")
        m = re.match(r"^expo_(day[137]|starter|pro|premium)(?:_(?:gb|eu|us|ca|au))?$", raw)
        if not m:
            return None
        tier = m.group(1)
        if tier in ("day1", "day3", "day7"):
            return tier
        return None

    @staticmethod
    def _deactivate_non_canonical_packages(db: Session, *, now: datetime) -> None:
        plans = db.execute(select(Plan).where(Plan.service_kind == EXPO_SERVICE_CODE)).scalars().all()
        for plan in plans:
            code = str(plan.code or "")
            if code in CANONICAL_EXPO_CODES:
                continue
            plan.is_active = False
            plan.updated_at = now
            db.add(plan)
            expo_pkg = db.execute(select(ExpoPackage).where(ExpoPackage.plan_id == plan.id)).scalar_one_or_none()
            if expo_pkg is not None:
                expo_pkg.is_active = False
                expo_pkg.updated_at = now
                db.add(expo_pkg)

    @staticmethod
    def _repoint_booths_to_canonical(db: Session, *, now: datetime, canonical_by_tier: dict[str, ExpoPackage]) -> None:
        booths = db.execute(select(ExpoBooth).where(ExpoBooth.package_id.is_not(None))).scalars().all()
        for booth in booths:
            old = db.get(ExpoPackage, booth.package_id)
            if old is None:
                continue
            if old.market_zone == "all" and old.tier in canonical_by_tier and old.id == canonical_by_tier[old.tier].id:
                continue
            plan = db.get(Plan, old.plan_id) if old.plan_id else None
            tier = old.tier if old.tier in canonical_by_tier else ExpoSeedService._tier_from_plan_code(plan.code if plan else "")
            if not tier or tier not in canonical_by_tier:
                continue
            target = canonical_by_tier[tier]
            if booth.package_id == target.id:
                continue
            booth.package_id = target.id
            booth.updated_at = now
            db.add(booth)

    @staticmethod
    def _ensure_packages(db: Session) -> None:
        now = datetime.utcnow()
        canonical_by_tier: dict[str, ExpoPackage] = {}

        for pkg in PACKAGE_TIERS:
            code = str(pkg["code"])
            features_json = json.dumps(pkg["features"])
            days = int(pkg["duration_days"])
            gbp = int(pkg["prices"]["GBP"])
            description = (
                f"VoxBulk Expo — {pkg['name']} ({days} day{'s' if days != 1 else ''} active) "
                f"per exhibition (one-time; optional annual available)"
            )
            plan = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
            if plan is None:
                plan = Plan(
                    id=str(uuid.uuid4()),
                    code=code,
                    name=pkg["name"],
                    price_gbp_pence=gbp,
                    interval="one_time",
                    description=description,
                    features_json=features_json,
                    calls_included=0,
                    whatsapp_included=0,
                    service_kind=EXPO_SERVICE_CODE,
                    is_active=True,
                    is_featured=bool(pkg.get("featured")),
                    sort_order=int(pkg["order"]),
                    created_at=now,
                    updated_at=now,
                )
                db.add(plan)
                db.flush()
            elif not bool(plan.is_frozen):
                plan.name = pkg["name"]
                plan.service_kind = EXPO_SERVICE_CODE
                plan.description = description
                plan.features_json = features_json
                plan.interval = "one_time"
                plan.is_active = True
                plan.is_featured = bool(pkg.get("featured"))
                plan.sort_order = int(pkg["order"])
                plan.price_gbp_pence = gbp
                plan.updated_at = now
                db.add(plan)

            for currency, amount in pkg["prices"].items():
                price_row = db.execute(
                    select(PlanPrice).where(PlanPrice.plan_id == plan.id, PlanPrice.currency == currency)
                ).scalar_one_or_none()
                if price_row is None:
                    db.add(
                        PlanPrice(
                            id=str(uuid.uuid4()),
                            plan_id=plan.id,
                            currency=currency,
                            monthly_price_minor=int(amount),
                            yearly_price_minor=None,
                            per_min_minor=0,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                elif not bool(plan.is_frozen):
                    # Keep admin-edited amounts; only fill missing one-time if empty.
                    if price_row.monthly_price_minor is None:
                        price_row.monthly_price_minor = int(amount)
                        price_row.updated_at = now
                        db.add(price_row)

            expo_pkg = db.execute(select(ExpoPackage).where(ExpoPackage.plan_id == plan.id)).scalar_one_or_none()
            if expo_pkg is None:
                expo_pkg = ExpoPackage(
                    id=str(uuid.uuid4()),
                    plan_id=plan.id,
                    market_zone="all",
                    tier=pkg["tier"],
                    duration_days=days,
                    max_booths=int(pkg["max_booths"]),
                    max_assets=int(pkg["max_assets"]),
                    lead_scoring_enabled=bool(pkg["lead_scoring"]),
                    post_show_followup_enabled=bool(pkg["post_show_followup"]),
                    post_event_survey_enabled=bool(pkg["post_event_survey"]),
                    ai_summary_report_enabled=bool(pkg["ai_summary"]),
                    display_order=int(pkg["order"]),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(expo_pkg)
                db.flush()
            elif not bool(plan.is_frozen):
                expo_pkg.market_zone = "all"
                expo_pkg.tier = pkg["tier"]
                expo_pkg.duration_days = days
                expo_pkg.max_booths = int(pkg["max_booths"])
                expo_pkg.max_assets = int(pkg["max_assets"])
                expo_pkg.lead_scoring_enabled = bool(pkg["lead_scoring"])
                expo_pkg.post_show_followup_enabled = bool(pkg["post_show_followup"])
                expo_pkg.post_event_survey_enabled = bool(pkg["post_event_survey"])
                expo_pkg.ai_summary_report_enabled = bool(pkg["ai_summary"])
                expo_pkg.display_order = int(pkg["order"])
                expo_pkg.is_active = True
                expo_pkg.updated_at = now
                db.add(expo_pkg)
            canonical_by_tier[str(pkg["tier"])] = expo_pkg

        ExpoSeedService._deactivate_non_canonical_packages(db, now=now)
        ExpoSeedService._repoint_booths_to_canonical(db, now=now, canonical_by_tier=canonical_by_tier)
        db.flush()
