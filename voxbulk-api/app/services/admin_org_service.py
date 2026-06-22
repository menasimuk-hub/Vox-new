from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dentally_appointment import DentallyAppointment
from app.models.branch import Branch
from app.models.membership import OrganisationMembership
from app.models.category import Category
from app.models.organisation import Organisation
from app.models.patient import Patient
from app.models.plan import Plan
from app.models.recovery_job import RecoveryJob
from app.models.subscription import Subscription
from app.models.user import User
from app.services.market_zone import country_column_matches_zone, country_to_zone, normalize_zone


@dataclass(frozen=True)
class AdminOrganisationSummary:
    id: str
    name: str
    created_at: datetime
    is_suspended: bool
    profile_notes: str | None
    category_id: str | None
    category_name: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    county_state: str | None
    postcode: str | None
    country: str | None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    website: str | None
    branch_count: int
    user_count: int
    patient_count: int
    appointment_count: int
    recovery_job_count: int
    subscription_status: str | None
    plan_code: str | None
    plan_name: str | None
    wallet_balance_pence: int = 0


class AdminOrganisationService:
    @staticmethod
    def list_orgs(
        db: Session,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        zone: str | None = None,
    ) -> list[AdminOrganisationSummary]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))

        orgs_stmt = select(Organisation).order_by(Organisation.created_at.desc())
        if search:
            orgs_stmt = orgs_stmt.where(Organisation.name.ilike(f"%{search.strip()}%"))
        zone_key = normalize_zone(zone)
        if zone_key:
            orgs_stmt = orgs_stmt.where(country_column_matches_zone(Organisation.country, zone_key))

        org_rows = list(db.execute(orgs_stmt.limit(limit).offset(offset)).scalars().all())
        if not org_rows:
            return []

        org_ids = [o.id for o in org_rows]
        category_ids = [o.category_id for o in org_rows if getattr(o, "category_id", None)]

        categories: dict[str, Category] = {}
        if category_ids:
            categories = {
                c.id: c
                for c in db.execute(select(Category).where(Category.id.in_(list(set(category_ids))))).scalars().all()
            }

        def _count_by(model, col):
            return dict(
                db.execute(select(col, func.count()).where(col.in_(org_ids)).group_by(col)).all()
            )

        branch_counts = _count_by(Branch, Branch.org_id)
        patient_counts = _count_by(Patient, Patient.org_id)
        appt_counts = _count_by(DentallyAppointment, DentallyAppointment.org_id)
        job_counts = _count_by(RecoveryJob, RecoveryJob.org_id)

        # Users count is via membership table.
        user_counts = dict(
            db.execute(
                select(OrganisationMembership.org_id, func.count(func.distinct(OrganisationMembership.user_id)))
                .where(OrganisationMembership.org_id.in_(org_ids))
                .group_by(OrganisationMembership.org_id)
            ).all()
        )

        # Subscription/plan: keep it summary-level; pick "latest" subscription by created_at if multiple.
        sub_rows = list(
            db.execute(
                select(Subscription.org_id, Subscription.status, Subscription.plan_id, Subscription.created_at)
                .where(Subscription.org_id.in_(org_ids))
                .order_by(Subscription.org_id.asc(), Subscription.created_at.desc())
            ).all()
        )
        latest_sub: dict[str, tuple[str, str]] = {}
        for r in sub_rows:
            if r.org_id not in latest_sub:
                latest_sub[r.org_id] = (r.status, r.plan_id)

        plan_ids = list({plan_id for (_, plan_id) in latest_sub.values() if plan_id})
        plans = {}
        if plan_ids:
            plans = {p.id: p for p in db.execute(select(Plan).where(Plan.id.in_(plan_ids))).scalars().all()}

        out: list[AdminOrganisationSummary] = []
        for org in org_rows:
            sub = latest_sub.get(org.id)
            plan = plans.get(sub[1]) if sub else None
            cat = categories.get(getattr(org, "category_id", None))
            out.append(
                AdminOrganisationSummary(
                    id=org.id,
                    name=org.name,
                    created_at=org.created_at,
                    is_suspended=bool(org.is_suspended),
                    profile_notes=org.profile_notes,
                    category_id=getattr(org, "category_id", None),
                    category_name=cat.name if cat else None,
                    address_line1=getattr(org, "address_line1", None),
                    address_line2=getattr(org, "address_line2", None),
                    city=getattr(org, "city", None),
                    county_state=getattr(org, "county_state", None),
                    postcode=getattr(org, "postcode", None),
                    country=getattr(org, "country", None),
                    contact_name=getattr(org, "contact_name", None),
                    contact_email=getattr(org, "contact_email", None),
                    contact_phone=getattr(org, "contact_phone", None),
                    website=getattr(org, "website", None),
                    branch_count=int(branch_counts.get(org.id, 0)),
                    user_count=int(user_counts.get(org.id, 0)),
                    patient_count=int(patient_counts.get(org.id, 0)),
                    appointment_count=int(appt_counts.get(org.id, 0)),
                    recovery_job_count=int(job_counts.get(org.id, 0)),
                    subscription_status=sub[0] if sub else None,
                    plan_code=plan.code if plan else None,
                    plan_name=plan.name if plan else None,
                    wallet_balance_pence=int(getattr(org, "wallet_balance_pence", 0) or 0),
                )
            )
        return out

    @staticmethod
    def get_org_summary(db: Session, *, org_id: str) -> AdminOrganisationSummary | None:
        org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
        if org is None:
            return None

        branch_count = db.execute(select(func.count()).select_from(Branch).where(Branch.org_id == org_id)).scalar_one()
        patient_count = db.execute(select(func.count()).select_from(Patient).where(Patient.org_id == org_id)).scalar_one()
        appointment_count = db.execute(select(func.count()).select_from(DentallyAppointment).where(DentallyAppointment.org_id == org_id)).scalar_one()
        recovery_job_count = db.execute(select(func.count()).select_from(RecoveryJob).where(RecoveryJob.org_id == org_id)).scalar_one()

        user_count = db.execute(
            select(func.count(func.distinct(OrganisationMembership.user_id)))
            .select_from(OrganisationMembership)
            .where(OrganisationMembership.org_id == org_id)
        ).scalar_one()

        sub = db.execute(
            select(Subscription).where(Subscription.org_id == org_id).order_by(Subscription.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        plan = None
        if sub is not None:
            plan = db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one_or_none()

        cat_name: str | None = None
        cat_id = getattr(org, "category_id", None)
        if cat_id:
            cat_name = db.execute(select(Category.name).where(Category.id == cat_id)).scalar_one_or_none()

        return AdminOrganisationSummary(
            id=org.id,
            name=org.name,
            created_at=org.created_at,
            is_suspended=bool(org.is_suspended),
            profile_notes=org.profile_notes,
            category_id=cat_id,
            category_name=cat_name,
            address_line1=getattr(org, "address_line1", None),
            address_line2=getattr(org, "address_line2", None),
            city=getattr(org, "city", None),
            county_state=getattr(org, "county_state", None),
            postcode=getattr(org, "postcode", None),
            country=getattr(org, "country", None),
            contact_name=getattr(org, "contact_name", None),
            contact_email=getattr(org, "contact_email", None),
            contact_phone=getattr(org, "contact_phone", None),
            website=getattr(org, "website", None),
            branch_count=int(branch_count),
            user_count=int(user_count),
            patient_count=int(patient_count),
            appointment_count=int(appointment_count),
            recovery_job_count=int(recovery_job_count),
            subscription_status=sub.status if sub else None,
            plan_code=plan.code if plan else None,
            plan_name=plan.name if plan else None,
            wallet_balance_pence=int(getattr(org, "wallet_balance_pence", 0) or 0),
        )

