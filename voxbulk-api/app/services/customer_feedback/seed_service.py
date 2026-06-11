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
]

PACKAGE_TIERS: list[dict] = [
    {
        "tier": "starter",
        "name": "Starter",
        "locations": 1,
        "units": 200,
        "order": 10,
        "featured": False,
        "price_minor": 4900,
        "features": [
            "1 location",
            "200 surveys/mo",
            "Monthly report",
            "Email support",
        ],
    },
    {
        "tier": "growth",
        "name": "Growth",
        "locations": 3,
        "units": 600,
        "order": 20,
        "featured": True,
        "price_minor": 9900,
        "features": [
            "3 locations",
            "600 surveys/mo",
            "Weekly report",
            "Live dashboard",
            "Priority support",
        ],
    },
    {
        "tier": "pro",
        "name": "Pro",
        "locations": 10,
        "units": 2500,
        "order": 30,
        "featured": False,
        "price_minor": 19900,
        "features": [
            "10 locations",
            "2500 surveys",
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
        FeedbackSeedService._seed_wa_sender_if_needed(db)
        FeedbackSeedService._ensure_packages(db)
        db.commit()

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

    @staticmethod
    def _seed_wa_sender_if_needed(db: Session) -> None:
        sender = db.execute(select(FeedbackWaSender).where(FeedbackWaSender.country_code == "gb")).scalar_one_or_none()
        if sender is None:
            db.add(
                FeedbackWaSender(
                    id=str(uuid.uuid4()),
                    country_code="gb",
                    phone_e164="+447700900000",
                    created_at=datetime.utcnow(),
                )
            )

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
                        display_order=int(pkg["order"]),
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                fb_pkg.market_zone = pkg["zone"]
                fb_pkg.max_locations = int(pkg["locations"])
                fb_pkg.wa_units_included = int(pkg["units"])
                fb_pkg.display_order = int(pkg["order"])
                fb_pkg.is_active = True
                fb_pkg.updated_at = now
