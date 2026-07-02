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

# Legacy DEFAULT_INDUSTRIES rows superseded by INDUSTRY_CATALOG — hide from customer wizard.
LEGACY_INDUSTRY_SLUGS_TO_HIDE: frozenset[str] = frozenset(
    {
        "healthcare",
        "ecommerce",
        "finance",
        "hospitality",
        "education",
        "saas",
        "services",
        "general",
    }
)

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
            "Overall service satisfaction",
            "Visit met your needs",
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
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            "Overall service satisfaction",
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
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            "Visit met your needs",
            "Overall service satisfaction",
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
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            "Visit met your needs",
            "Overall service satisfaction",
            "Check-out experience",
            "Room temperature control",
            "Wi-Fi quality",
            "Bed comfort",
            "Bathroom cleanliness",
            "Parking experience",
            "Concierge/help desk rating",
            "Pool/gym facilities",
            "In-room dining",
            "Evening turndown service",
            "Overall stay rating",
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            "Overall service satisfaction",
            "Tenancy needs met",
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
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            "Overall service satisfaction",
            "Purchase met your needs",
            "Website experience",
            "Order accuracy",
            "Delivery speed",
            "Checkout experience",
            "Product description accuracy",
            "Customer service rating",
            "Checkout clarity",
            "In-store experience",
            "Click & collect experience",
            "Refund speed",
            "Overall shopping rating",
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            "Overall service satisfaction",
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
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            "Overall service satisfaction",
            "Booking experience",
            "Support quality",
            "Visit met your needs",
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
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            "Overall service satisfaction",
            "Onboarding experience",
            "Billing transparency",
            "Service satisfaction today",
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
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            "Overall service satisfaction",
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
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
        ],
    },
    {
        "slug": "financial_services",
        "name": "Financial Services",
        "sort_order": 105,
        "services": [
            "Advice clarity",
            "Product suitability",
            "Adviser professionalism",
            "Response time",
            "Value for money",
            "Onboarding experience",
            "Overall service satisfaction",
            "Communication quality",
            "Trust & confidence",
            "Compliance & transparency",
            "Digital platform rating",
            "Application process",
            "Mortgage/loan handling",
            "Claims experience",
            "Renewal process",
            "Documentation clarity",
            "Fee transparency",
            "Switch/transfer experience",
            "Complaint handling",
            "Overall service rating",
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
        ],
    },
    {
        "slug": "logistics_delivery",
        "name": "Logistics & Delivery",
        "sort_order": 106,
        "services": [
            "Delivery speed",
            "Packaging condition",
            "Driver attitude",
            "Delivery accuracy",
            "Communication/tracking",
            "Overall service satisfaction",
            "Collection experience",
            "Returns process",
            "Value for money",
            "Delivery met your needs",
            "Safe place delivery rating",
            "Missed delivery handling",
            "Customer service quality",
            "App/portal experience",
            "Proof of delivery satisfaction",
            "Fragile item handling",
            "Same-day service rating",
            "International delivery rating",
            "Business account experience",
            "Overall delivery rating",
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
        ],
    },
    {
        "slug": "events_entertainment",
        "name": "Events & Entertainment",
        "sort_order": 107,
        "services": [
            "Event organisation",
            "Venue quality",
            "Staff friendliness",
            "Value for money",
            "Overall service satisfaction",
            "Visit met your needs",
            "Ticketing/booking experience",
            "Queue management",
            "Food & drink quality",
            "Parking & transport",
            "Safety & security feel",
            "Speaker/performer rating",
            "Sound & AV quality",
            "Networking opportunity",
            "Programme/schedule quality",
            "Signage & navigation",
            "Accessibility provision",
            "Merchandise experience",
            "Post-event communication",
            "Overall event rating",
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            "Inclusion & belonging",
            "Career progression",
            "Training quality",
            "Goal clarity",
            "Role clarity",
            "Job satisfaction",
            "Internal communication",
            "Pay & benefits fairness",
            "Remote/hybrid flexibility",
            "Psychological safety",
            "Overall employee experience",
            "Issue resolution rating",
            "Information clarity",
            "Hand-off wait time",
            "Facility access comfort",
            "Overall experience today",
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
            services_updated: list[str] = []
            expected_slugs: set[str] = set()
            for sort_idx, service_name in enumerate(item.get("services") or [], start=1):
                service_slug = _service_slug(service_name)
                expected_slugs.add(service_slug)
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
                    changed = False
                    if st.name != str(service_name):
                        st.name = str(service_name)
                        changed = True
                    desc = f"{service_name} feedback for {item['name']}."
                    if st.description != desc:
                        st.description = desc
                        changed = True
                    if int(st.sort_order or 0) != sort_idx * 10:
                        st.sort_order = sort_idx * 10
                        changed = True
                    if not st.is_active:
                        st.is_active = True
                        changed = True
                    if changed:
                        st.updated_at = now
                        db.add(st)
                        services_updated.append(str(service_name))
                service_rows.append({"id": st.id, "slug": st.slug, "name": st.name})

            for orphan in db.execute(
                select(SurveyType).where(SurveyType.industry_id == row.id)
            ).scalars():
                if orphan.slug in expected_slugs:
                    continue
                if orphan.is_active:
                    orphan.is_active = False
                    orphan.updated_at = now
                    db.add(orphan)

            industry_details.append(
                {
                    "slug": row.slug,
                    "name": row.name,
                    "status": "created" if industry_was_created else "existing",
                    "active_service_count": len(expected_slugs),
                    "services_created": services_created,
                    "services_skipped": services_skipped,
                    "services_updated": services_updated,
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

        for legacy_slug in LEGACY_INDUSTRY_SLUGS_TO_HIDE:
            legacy = db.execute(select(Industry).where(Industry.slug == legacy_slug)).scalar_one_or_none()
            if legacy is None:
                continue
            if not bool(getattr(legacy, "is_hidden", False)):
                legacy.is_hidden = True
                legacy.updated_at = now
                db.add(legacy)

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
