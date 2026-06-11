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

PACKAGE_SEEDS: list[dict] = [
    {"code": "cf_starter_gb", "name": "Customer feedback Starter", "zone": "gb", "locations": 1, "units": 100, "price_pence": 4900, "order": 10},
    {"code": "cf_growth_gb", "name": "Customer feedback Growth", "zone": "gb", "locations": 3, "units": 200, "price_pence": 9900, "order": 20},
    {"code": "cf_starter_us", "name": "Customer feedback Starter (US)", "zone": "us", "locations": 1, "units": 100, "price_pence": 5900, "order": 10},
    {"code": "cf_starter_ca", "name": "Customer feedback Starter (CA)", "zone": "ca", "locations": 1, "units": 100, "price_pence": 6900, "order": 10},
    {"code": "cf_starter_au", "name": "Customer feedback Starter (AU)", "zone": "au", "locations": 1, "units": 100, "price_pence": 7900, "order": 10},
]

ZONE_CURRENCY = {"gb": "GBP", "us": "USD", "ca": "CAD", "au": "AUD"}


def _slugify(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")[:60] or "type"


class FeedbackSeedService:
    @staticmethod
    def ensure_seeded(db: Session) -> None:
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
        sender = db.execute(select(FeedbackWaSender).where(FeedbackWaSender.country_code == "gb")).scalar_one_or_none()
        if sender is None:
            db.add(
                FeedbackWaSender(
                    id=str(uuid.uuid4()),
                    country_code="gb",
                    phone_e164="+447700900000",
                    created_at=now,
                )
            )
        for pkg in PACKAGE_SEEDS:
            plan = db.execute(select(Plan).where(Plan.code == pkg["code"])).scalar_one_or_none()
            if plan is None:
                currency = ZONE_CURRENCY.get(pkg["zone"], "GBP")
                plan = Plan(
                    id=str(uuid.uuid4()),
                    code=pkg["code"],
                    name=pkg["name"],
                    price_gbp_pence=int(pkg["price_pence"]),
                    interval="monthly",
                    description=f"WhatsApp QR feedback — {pkg['locations']} location(s), {pkg['units']} WA surveys/month",
                    features_json=json.dumps([
                        f"{pkg['locations']} QR location(s)",
                        f"{pkg['units']} WhatsApp survey units / month",
                        "Direct Debit only — no overage",
                    ]),
                    calls_included=0,
                    whatsapp_included=int(pkg["units"]),
                    service_kind=FEEDBACK_SERVICE_CODE,
                    is_active=True,
                    sort_order=int(pkg["order"]),
                    created_at=now,
                    updated_at=now,
                )
                db.add(plan)
                db.flush()
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
        db.commit()
