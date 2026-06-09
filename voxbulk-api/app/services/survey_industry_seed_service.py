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
from app.services.industry_service import IndustryService
from app.services.survey_system_template_service import SurveySystemTemplateService

INDUSTRY_CATALOG: list[dict[str, Any]] = [
    {
        "slug": "healthcare_dental",
        "name": "Healthcare & Dental",
        "sort_order": 10,
        "services": [
            "Post-visit satisfaction",
            "Wait time rating",
            "Staff attitude",
            "Cleanliness",
            "Treatment outcome",
            "Pricing fairness",
            "Would recommend",
            "Return intent",
            "Booking experience",
            "Communication clarity",
            "Appointment availability",
            "Pain management satisfaction",
            "Explanation of treatment",
            "Waiting area comfort",
            "Reception staff rating",
            "Follow-up care quality",
            "Hygienist satisfaction",
            "Parking & accessibility",
            "Online/app experience",
            "Overall care rating",
        ],
    },
    {
        "slug": "recruitment_staffing",
        "name": "Recruitment & Staffing",
        "sort_order": 20,
        "services": [
            "Candidate experience",
            "Interview process rating",
            "Consultant rating",
            "Placement satisfaction",
            "Communication quality",
            "Employer satisfaction",
            "Speed of placement",
            "Professionalism",
            "Would recommend",
            "Job match quality",
            "CV support quality",
            "Onboarding support",
            "Candidate quality (employer)",
            "Time-to-hire satisfaction",
            "Post-placement check-in",
            "Salary negotiation support",
            "Interview preparation quality",
            "Transparency of process",
            "Long-term fit rating",
            "Overall service rating",
        ],
    },
    {
        "slug": "hospitality_food",
        "name": "Hospitality & Food",
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
            "Dietary/allergy handling",
            "Drink quality",
            "Menu variety",
            "Wait for table",
            "Bill accuracy",
            "Noise level",
            "Outdoor seating experience",
            "Takeaway packaging",
            "Delivery experience",
            "Overall dining rating",
        ],
    },
    {
        "slug": "hotel_accommodation",
        "name": "Hotel & Accommodation",
        "sort_order": 40,
        "services": [
            "Check-in experience",
            "Room cleanliness",
            "Breakfast quality",
            "Staff friendliness",
            "Value for money",
            "Noise & comfort",
            "Facilities rating",
            "Return intent",
            "Would recommend",
            "Check-out experience",
            "Room temperature control",
            "Wi‑Fi quality",
            "Bed comfort",
            "Bathroom cleanliness",
            "Parking experience",
            "Concierge/help desk rating",
            "Pool/gym facilities",
            "In-room dining",
            "Evening turndown service",
            "Overall stay rating",
        ],
    },
    {
        "slug": "property_lettings",
        "name": "Property & Lettings",
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
            "Safety & security perception",
            "Deposit handling",
            "Inventory accuracy",
            "Move-out process",
            "Tenant communication quality",
            "Emergency response speed",
            "Online portal experience",
            "Referencing process",
            "Rent review fairness",
            "Overall tenancy rating",
        ],
    },
    {
        "slug": "retail_ecommerce",
        "name": "Retail & E-Commerce",
        "sort_order": 60,
        "services": [
            "Product quality",
            "Delivery experience",
            "Packaging quality",
            "Returns process",
            "Value for money",
            "Staff helpfulness",
            "Stock availability",
            "Would recommend",
            "Repeat purchase intent",
            "Website experience",
            "Order accuracy",
            "Delivery speed",
            "Checkout experience",
            "Product description accuracy",
            "Customer service rating",
            "Loyalty programme value",
            "In-store experience",
            "Click & collect experience",
            "Refund speed",
            "Overall shopping rating",
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
            "MOT experience",
            "Courtesy car availability",
            "Parts quality",
            "Diagnostic accuracy",
            "Invoice clarity",
            "Warranty handling",
            "Collection/drop-off experience",
            "Upsell pressure rating",
            "Post-service follow-up",
            "Overall garage rating",
        ],
    },
    {
        "slug": "education_training",
        "name": "Education & Training",
        "sort_order": 80,
        "services": [
            "Course quality",
            "Trainer rating",
            "Learning outcome",
            "Facilities",
            "Value for money",
            "Course material quality",
            "Would recommend",
            "Booking experience",
            "Support quality",
            "Return intent",
            "Post-course resources",
            "Group size satisfaction",
            "Pace of delivery",
            "Online learning experience",
            "Assessment fairness",
            "Certificate/accreditation value",
            "Pre-course communication",
            "Trainer knowledge depth",
            "Practical vs theory balance",
            "Overall course rating",
        ],
    },
    {
        "slug": "legal_accountancy",
        "name": "Legal & Accountancy",
        "sort_order": 90,
        "services": [
            "Communication clarity",
            "Matter handling",
            "Value for money",
            "Case/matter outcome",
            "Staff professionalism",
            "Response time",
            "Would recommend",
            "Onboarding experience",
            "Billing transparency",
            "Referral likelihood",
            "Expectation vs outcome",
            "Document handling",
            "Jargon avoidance",
            "Deadline adherence",
            "Partner/senior access",
            "Digital tools experience",
            "Tax return satisfaction",
            "Court/hearing preparation",
            "Confidentiality confidence",
            "Overall service rating",
        ],
    },
    {
        "slug": "fitness_wellness",
        "name": "Fitness & Wellness",
        "sort_order": 100,
        "services": [
            "Session quality",
            "Trainer attitude",
            "Facilities rating",
            "Cleanliness",
            "Value for money",
            "Class variety",
            "Booking experience",
            "Staff friendliness",
            "Would recommend",
            "Membership value",
            "Equipment availability",
            "Changing room quality",
            "App/online portal rating",
            "Personal training value",
            "Class size satisfaction",
            "Parking & access",
            "Nutrition/supplement advice",
            "Injury support handling",
            "Peak time crowding",
            "Overall experience rating",
        ],
    },
    {
        "slug": "financial_services",
        "name": "Financial Services",
        "sort_order": 105,
        "services": [
            "Advice clarity",
            "Product suitability",
            "Adviser rating",
            "Value for money",
            "Response time",
            "Would recommend",
            "Onboarding experience",
            "Billing transparency",
            "Referral likelihood",
            "Trust & confidence",
            "Complaint handling",
            "Digital banking experience",
            "Loan/mortgage process",
            "Investment communication",
            "Fee clarity",
            "Branch experience",
            "Phone support quality",
            "Document delivery speed",
            "Regulatory communication clarity",
            "Overall service rating",
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
        industry_details: list[dict[str, Any]] = []

        for item in INDUSTRY_CATALOG:
            slug = str(item["slug"])
            if IndustryService.is_slug_tombstoned(db, slug):
                continue
            row = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
            industry_was_created = False
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
                industry_was_created = True
            else:
                industries_existing += 1

            service_rows: list[dict[str, str]] = []
            services_created: list[str] = []
            services_skipped: list[str] = []
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
                    services_created.append(str(service_name))
                else:
                    types_existing += 1
                    services_skipped.append(str(service_name))
                service_rows.append({"id": st.id, "slug": st.slug, "name": st.name})

            industry_details.append(
                {
                    "slug": row.slug,
                    "name": row.name,
                    "status": "created" if industry_was_created else "existing",
                    "services_created": services_created,
                    "services_skipped": services_skipped,
                }
            )

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
            "industry_details": industry_details,
            "system_industry": system,
        }
