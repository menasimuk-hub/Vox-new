"""Idempotent seed for WA Survey industries, service tags, and system templates."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.services.survey_system_template_service import SurveySystemTemplateService

INDUSTRY_CATALOG: list[dict[str, Any]] = [
    {
        "slug": "healthcare_dental",
        "name": "Healthcare & dental",
        "sort_order": 10,
        "services": [
            "Post-visit",
            "Wait time",
            "Staff attitude",
            "Cleanliness",
            "Treatment outcome",
            "Pricing",
            "Would recommend",
            "Return intent",
            "Booking experience",
            "Communication",
        ],
    },
    {
        "slug": "recruitment_staffing",
        "name": "Recruitment & staffing",
        "sort_order": 20,
        "services": [
            "Candidate experience",
            "Interview process",
            "Consultant rating",
            "Placement satisfaction",
            "Communication",
            "Employer satisfaction",
            "Speed of placement",
            "Professionalism",
            "Would recommend",
            "Job match quality",
        ],
    },
    {
        "slug": "hospitality_food",
        "name": "Hospitality & food",
        "sort_order": 30,
        "services": [
            "Food quality",
            "Service speed",
            "Staff friendliness",
            "Cleanliness",
            "Value for money",
            "Ambience",
            "Booking experience",
            "Return intent",
            "Would recommend",
            "Portion size",
        ],
    },
    {
        "slug": "hotel_accommodation",
        "name": "Hotel & accommodation",
        "sort_order": 40,
        "services": [
            "Check-in experience",
            "Room cleanliness",
            "Breakfast quality",
            "Staff friendliness",
            "Value for money",
            "Noise & comfort",
            "Facilities",
            "Return intent",
            "Would recommend",
            "Check-out experience",
        ],
    },
    {
        "slug": "property_lettings",
        "name": "Property & lettings",
        "sort_order": 50,
        "services": [
            "Viewing experience",
            "Move-in condition",
            "Maintenance response",
            "Communication",
            "Value for money",
            "Property management",
            "Would recommend",
            "Renewal intent",
            "Agent professionalism",
            "Issue resolution",
        ],
    },
    {
        "slug": "retail_ecommerce",
        "name": "Retail & e-commerce",
        "sort_order": 60,
        "services": [
            "Product quality",
            "Delivery experience",
            "Packaging",
            "Returns process",
            "Value for money",
            "Staff helpfulness",
            "Stock availability",
            "Would recommend",
            "Repeat purchase intent",
            "Website experience",
        ],
    },
    {
        "slug": "automotive",
        "name": "Automotive",
        "sort_order": 70,
        "services": [
            "Work quality",
            "Explanation of work",
            "Punctuality",
            "Pricing transparency",
            "Vehicle cleanliness",
            "Booking experience",
            "Staff attitude",
            "Value for money",
            "Would recommend",
            "Turnaround time",
        ],
    },
    {
        "slug": "education_training",
        "name": "Education & training",
        "sort_order": 80,
        "services": [
            "Course quality",
            "Trainer rating",
            "Learning outcome",
            "Facilities",
            "Value for money",
            "Course material",
            "Would recommend",
            "Booking experience",
            "Support quality",
            "Return intent",
        ],
    },
    {
        "slug": "legal_accountancy",
        "name": "Legal & accountancy",
        "sort_order": 90,
        "services": [
            "Communication clarity",
            "Matter handling",
            "Value for money",
            "Case outcome",
            "Staff professionalism",
            "Response time",
            "Would recommend",
            "Onboarding experience",
            "Billing transparency",
            "Referral likelihood",
        ],
    },
    {
        "slug": "fitness_wellness",
        "name": "Fitness & wellness",
        "sort_order": 100,
        "services": [
            "Session quality",
            "Trainer attitude",
            "Facilities",
            "Cleanliness",
            "Value for money",
            "Class variety",
            "Booking experience",
            "Staff friendliness",
            "Would recommend",
            "Membership value",
        ],
    },
    {
        "slug": "employee_survey",
        "name": "Employee Survey",
        "sort_order": 110,
        "services": [
            "Morale",
            "Work-life balance",
            "Feeling valued",
            "Workload",
            "Motivation",
            "Manager communication",
            "Manager fairness",
            "Recognition",
            "Team collaboration",
            "Inclusion",
            "Career progression",
            "Training quality",
            "Goal clarity",
            "Role clarity",
            "Job satisfaction",
            "Internal communication",
        ],
    },
]


def _service_slug(name: str) -> str:
    token = re.sub(r"[^a-z0-9_]+", "_", str(name or "").strip().lower()).strip("_")
    return token[:64] or "service"


class SurveyIndustrySeedService:
    @staticmethod
    def ensure_catalog(db: Session) -> dict[str, Any]:
        SurveySystemTemplateService.ensure_system_survey_types(db)
        now = datetime.utcnow()
        industries_created = 0
        industries_existing = 0
        types_created = 0
        types_existing = 0
        industries_out: list[dict[str, Any]] = []

        for item in INDUSTRY_CATALOG:
            slug = str(item["slug"])
            row = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
            if row is None:
                row = Industry(
                    id=str(uuid.uuid4()),
                    slug=slug,
                    name=str(item["name"]),
                    description=f"WA Survey services for {item['name']}.",
                    is_active=True,
                    is_hidden=False,
                    sort_order=int(item.get("sort_order") or 100),
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
                db.flush()
                industries_created += 1
            else:
                industries_existing += 1

            service_rows: list[dict[str, str]] = []
            for sort_idx, service_name in enumerate(item.get("services") or [], start=1):
                service_slug = _service_slug(service_name)
                st = db.execute(
                    select(SurveyType).where(
                        SurveyType.industry_id == row.id,
                        SurveyType.slug == service_slug,
                    )
                ).scalar_one_or_none()
                if st is None:
                    st = SurveyType(
                        id=str(uuid.uuid4()),
                        industry_id=row.id,
                        slug=service_slug,
                        name=str(service_name),
                        description=f"{service_name} feedback for {item['name']}.",
                        is_active=True,
                        default_length="standard",
                        min_length=4,
                        max_length=6,
                        supports_anonymous=True,
                        sort_order=sort_idx * 10,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(st)
                    db.flush()
                    types_created += 1
                else:
                    types_existing += 1
                service_rows.append({"id": st.id, "slug": st.slug, "name": st.name})

            industries_out.append(
                {
                    "id": row.id,
                    "slug": row.slug,
                    "name": row.name,
                    "service_count": len(service_rows),
                }
            )

        db.commit()
        system = SurveySystemTemplateService.list_admin(db)
        return {
            "ok": True,
            "industries_created": industries_created,
            "industries_existing": industries_existing,
            "survey_types_created": types_created,
            "survey_types_existing": types_existing,
            "industries": industries_out,
            "system_industry": system,
        }
