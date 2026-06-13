"""Seed Customer Feedback industries, survey types, packages, and UK WA sender."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    FEEDBACK_SERVICE_CODE,
    FeedbackIndustry,
    FeedbackPackage,
    FeedbackSurveyType,
    FeedbackWaSender,
)
from app.models.plan import Plan
from app.models.plan_price import PlanPrice

INDUSTRY_SEEDS: list[dict] = [
    {
        "slug": "restaurant",
        "name": "Restaurants & cafés",
        "types": [
            "Overall experience", "Would recommend", "Staff friendliness", "Value for money",
            "Cleanliness", "Wait time", "Service speed", "Communication", "Atmosphere", "Return intent",
            "Food quality", "Menu variety", "Portion size", "Drink quality", "Reservation experience",
            "Order accuracy", "Dietary options", "Kids experience", "Takeaway packaging", "Bill clarity",
        ],
    },
    {
        "slug": "retail",
        "name": "Retail shops",
        "types": [
            "Overall experience", "Would recommend", "Staff friendliness", "Value for money",
            "Cleanliness", "Wait time", "Service speed", "Communication", "Atmosphere", "Return intent",
            "Product quality", "Stock availability", "Store layout", "Fitting room experience", "Checkout speed",
            "Returns policy", "Promotions clarity", "Loyalty programme", "Online vs in-store", "Packaging",
        ],
    },
    {
        "slug": "salon",
        "name": "Salons & spas",
        "types": [
            "Overall experience", "Would recommend", "Staff friendliness", "Value for money",
            "Cleanliness", "Wait time", "Service speed", "Communication", "Atmosphere", "Return intent",
            "Treatment quality", "Stylist skill", "Product range", "Booking experience", "Hygiene standards",
            "Relaxation level", "Aftercare advice", "Consultation quality", "Pricing transparency", "Punctuality",
        ],
    },
    {
        "slug": "hotel",
        "name": "Hotels & hospitality",
        "types": [
            "Overall experience", "Would recommend", "Staff friendliness", "Value for money",
            "Cleanliness", "Wait time", "Service speed", "Communication", "Atmosphere", "Return intent",
            "Room cleanliness", "Bed comfort", "Breakfast quality", "Check-in experience", "Check-out experience",
            "Facilities", "Noise level", "Wi-Fi quality", "Concierge helpfulness", "Booking accuracy",
        ],
    },
    {
        "slug": "others",
        "name": "Others",
        "types": [
            "Overall experience", "Would recommend", "Staff friendliness", "Value for money",
            "Cleanliness", "Wait time", "Service speed", "Communication", "Atmosphere", "Return intent",
            "Product knowledge", "Problem resolution", "Booking experience", "Follow-up service", "Onboarding",
            "Accessibility", "Sustainability", "Trustworthiness", "Customisation", "First impression",
        ],
    },
    {
        "slug": "fitness",
        "name": "Fitness & gyms",
        "types": [
            "Overall experience", "Would recommend", "Staff friendliness", "Membership value",
            "Cleanliness", "Wait time", "Service speed", "Communication", "Atmosphere", "Return intent",
            "Equipment condition", "Class quality", "Trainer knowledge", "Changing room standards",
            "Booking / app experience", "Peak time capacity", "Personal training quality", "Nutrition advice",
            "Safety and hygiene", "Aftercare support",
        ],
    },
    {
        "slug": "events",
        "name": "Events & entertainment",
        "types": [
            "Overall experience", "Would recommend", "Staff friendliness", "Value for ticket price",
            "Cleanliness", "Wait time", "Service speed", "Communication", "Atmosphere", "Likelihood to attend again",
            "Event organisation", "Venue suitability", "Ticketing / entry experience", "Performer / content quality",
            "Sound and visuals", "Crowd management", "Food and drink options", "Seating / standing comfort",
            "Safety and security", "App or digital experience",
        ],
    },
]

PACKAGE_TIERS: list[dict] = [
    {
        "tier": "starter",
        "name": "Starter",
        "locations": 1,
        "units": 1000,
        "order": 10,
        "featured": False,
        "price_minor": 5900,
        "promo_cost_minor": 5,
        "features": [
            "1 location",
            "1000 survey triggers/mo",
            "Monthly report",
            "Email support",
        ],
    },
    {
        "tier": "pro",
        "name": "Pro",
        "locations": 5,
        "units": 3000,
        "order": 20,
        "featured": True,
        "price_minor": 12900,
        "promo_cost_minor": 4,
        "features": [
            "5 locations",
            "3000 survey triggers/mo",
            "Live dashboard",
            "Priority support",
        ],
    },
    {
        "tier": "business",
        "name": "Business",
        "locations": 20,
        "units": 10000,
        "order": 30,
        "featured": False,
        "price_minor": 24900,
        "promo_cost_minor": 3,
        "features": [
            "20 locations",
            "10000 survey triggers/mo",
            "Real-time dashboard",
            "Branded PDF report",
            "Dedicated account manager",
        ],
    },
]

PACKAGE_ZONES: list[dict] = [
    {"zone": "gb", "currency": "GBP"},
    {"zone": "eu", "currency": "EUR"},
    {"zone": "us", "currency": "USD"},
    {"zone": "ca", "currency": "CAD"},
    {"zone": "au", "currency": "AUD"},
]

PACKAGE_SEEDS: list[dict] = [
    {
        "code": f"cf_{tier['tier']}_{zone['zone']}",
        "name": tier["name"],
        "zone": zone["zone"],
        "currency": zone["currency"],
        "locations": tier["locations"],
        "units": tier["units"],
        "price_pence": tier["price_minor"],
        "promo_cost_minor": tier.get("promo_cost_minor", 5),
        "order": tier["order"],
        "featured": tier["featured"],
        "features": tier["features"],
    }
    for zone in PACKAGE_ZONES
    for tier in PACKAGE_TIERS
]


def _slugify(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")[:60] or "type"


class FeedbackSeedService:
    @staticmethod
    def ensure_seeded(db: Session) -> None:
        FeedbackSeedService._seed_industries_if_needed(db)
        FeedbackSeedService._ensure_extra_industries(db)
        FeedbackSeedService._seed_wa_sender_if_needed(db)
        FeedbackSeedService._sync_wa_sender_phones(db)
        FeedbackSeedService._ensure_packages(db)
        db.commit()

    @staticmethod
    def _sync_wa_sender_phones(db: Session) -> None:
        from app.services.customer_feedback.feedback_wa_phone import sync_feedback_wa_senders_from_telnyx

        sync_feedback_wa_senders_from_telnyx(db)

    @staticmethod
    def _ensure_extra_industries(db: Session) -> None:
        """Upsert industries added after initial seed (fitness, events)."""
        now = datetime.utcnow()
        extra_slugs = {"fitness", "events"}
        for ind in INDUSTRY_SEEDS:
            if ind["slug"] not in extra_slugs:
                continue
            row = db.execute(select(FeedbackIndustry).where(FeedbackIndustry.slug == ind["slug"])).scalar_one_or_none()
            if row is None:
                row = FeedbackIndustry(
                    id=str(uuid.uuid4()),
                    slug=ind["slug"],
                    name=ind["name"],
                    sort_order=100,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
                db.flush()
            for t_idx, type_name in enumerate(ind["types"]):
                slug = _slugify(type_name)
                existing_type = db.execute(
                    select(FeedbackSurveyType).where(
                        FeedbackSurveyType.industry_id == row.id,
                        FeedbackSurveyType.slug == slug,
                    )
                ).scalar_one_or_none()
                if existing_type is None:
                    db.add(
                        FeedbackSurveyType(
                            id=str(uuid.uuid4()),
                            industry_id=row.id,
                            slug=slug,
                            name=type_name,
                            sort_order=(t_idx + 1) * 10,
                            created_at=now,
                            updated_at=now,
                        )
                    )
            db.flush()

    @staticmethod
    def _seed_industries_if_needed(db: Session) -> None:
        existing = db.execute(select(FeedbackIndustry.id).limit(1)).scalar_one_or_none()
        if existing:
            return
        now = datetime.utcnow()
        for idx, ind in enumerate(INDUSTRY_SEEDS):
            industry = FeedbackIndustry(
                id=str(uuid.uuid4()),
                slug=ind["slug"],
                name=ind["name"],
                sort_order=(idx + 1) * 10,
                created_at=now,
                updated_at=now,
            )
            db.add(industry)
            db.flush()
            for t_idx, type_name in enumerate(ind["types"]):
                db.add(
                    FeedbackSurveyType(
                        id=str(uuid.uuid4()),
                        industry_id=industry.id,
                        slug=_slugify(type_name),
                        name=type_name,
                        sort_order=(t_idx + 1) * 10,
                        created_at=now,
                        updated_at=now,
                    )
                )
            db.flush()

    @staticmethod
    def _seed_wa_sender_if_needed(db: Session) -> None:
        """WhatsApp number is read from Telnyx integration (whatsapp_from), not seeded here."""
        return

    @staticmethod
    def _ensure_packages(db: Session) -> None:
        now = datetime.utcnow()
        for pkg in PACKAGE_SEEDS:
            currency = str(pkg["currency"])
            features_json = json.dumps(pkg["features"])
            description = (
                f"WhatsApp QR feedback — {pkg['name']} "
                f"({pkg['locations']} location(s), {pkg['units']} surveys/month)"
            )

            plan = db.execute(select(Plan).where(Plan.code == pkg["code"])).scalar_one_or_none()
            if plan is None:
                plan = Plan(
                    id=str(uuid.uuid4()),
                    code=pkg["code"],
                    name=pkg["name"],
                    price_gbp_pence=int(pkg["price_pence"]) if currency == "GBP" else 0,
                    interval="monthly",
                    description=description,
                    features_json=features_json,
                    calls_included=0,
                    whatsapp_included=int(pkg["units"]),
                    service_kind=FEEDBACK_SERVICE_CODE,
                    is_active=True,
                    is_featured=bool(pkg.get("featured")),
                    sort_order=int(pkg["order"]),
                    created_at=now,
                    updated_at=now,
                )
                db.add(plan)
                db.flush()
            else:
                plan.name = pkg["name"]
                if currency == "GBP":
                    plan.price_gbp_pence = int(pkg["price_pence"])
                plan.description = description
                plan.features_json = features_json
                plan.whatsapp_included = int(pkg["units"])
                plan.is_featured = bool(pkg.get("featured"))
                plan.sort_order = int(pkg["order"])
                plan.is_active = True
                plan.updated_at = now

            price_row = db.execute(
                select(PlanPrice).where(PlanPrice.plan_id == plan.id, PlanPrice.currency == currency)
            ).scalar_one_or_none()
            if price_row is None:
                db.add(
                    PlanPrice(
                        id=str(uuid.uuid4()),
                        plan_id=plan.id,
                        currency=currency,
                        monthly_price_minor=int(pkg["price_pence"]),
                        per_min_minor=0,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                price_row.monthly_price_minor = int(pkg["price_pence"])
                price_row.updated_at = now

            fb_pkg = db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == plan.id)).scalar_one_or_none()
            if fb_pkg is None:
                db.add(
                    FeedbackPackage(
                        id=str(uuid.uuid4()),
                        plan_id=plan.id,
                        market_zone=pkg["zone"],
                        max_locations=int(pkg["locations"]),
                        wa_units_included=int(pkg["units"]),
                        promo_message_cost_minor=int(pkg.get("promo_cost_minor") or 5),
                        display_order=int(pkg["order"]),
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                fb_pkg.market_zone = pkg["zone"]
                fb_pkg.max_locations = int(pkg["locations"])
                fb_pkg.wa_units_included = int(pkg["units"])
                fb_pkg.promo_message_cost_minor = int(pkg.get("promo_cost_minor") or 5)
                fb_pkg.display_order = int(pkg["order"])
                fb_pkg.is_active = True
                fb_pkg.updated_at = now
