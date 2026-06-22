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
from app.services.billing_access_service import BillingAccessService
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.market_zone import country_column_matches_zone, normalize_zone


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
    core_plan_code: str | None = None
    core_plan_name: str | None = None
    core_subscription_status: str | None = None
    feedback_plan_code: str | None = None
    feedback_plan_name: str | None = None
    feedback_subscription_status: str | None = None
    feedback_wa_units_included: int = 0
    feedback_wa_units_used: int = 0
    feedback_wa_units_remaining: int = 0
    wallet_balance_pence: int = 0


class AdminOrganisationService:
    @staticmethod
    def _subs_by_org_service(db: Session, org_ids: list[str]) -> dict[str, dict[str, Subscription]]:
        if not org_ids:
            return {}
        rows = list(
            db.execute(
                select(Subscription)
                .where(
                    Subscription.org_id.in_(org_ids),
                    Subscription.service_code.in_(("voxbulk", "customer_feedback")),
                )
                .order_by(
                    Subscription.org_id.asc(),
                    Subscription.service_code.asc(),
                    Subscription.updated_at.desc(),
                    Subscription.created_at.desc(),
                )
            )
            .scalars()
            .all()
        )
        out: dict[str, dict[str, Subscription]] = {}
        for sub in rows:
            bucket = out.setdefault(sub.org_id, {})
            code = str(sub.service_code or "voxbulk")
            if code not in bucket:
                bucket[code] = sub
        return out

    @staticmethod
    def _plan_fields_for_subs(
        db: Session,
        *,
        org_id: str,
        core_sub: Subscription | None,
        feedback_sub: Subscription | None,
    ) -> dict[str, object]:
        core_plan = db.get(Plan, core_sub.plan_id) if core_sub and core_sub.plan_id else None
        feedback_plan = db.get(Plan, feedback_sub.plan_id) if feedback_sub and feedback_sub.plan_id else None
        usage = FeedbackBillingService.get_current_usage(db, org_id) if feedback_sub else {}
        return {
            "subscription_status": core_sub.status if core_sub else None,
            "plan_code": core_plan.code if core_plan else None,
            "plan_name": core_plan.name if core_plan else None,
            "core_plan_code": core_plan.code if core_plan else None,
            "core_plan_name": core_plan.name if core_plan else None,
            "core_subscription_status": core_sub.status if core_sub else None,
            "feedback_plan_code": feedback_plan.code if feedback_plan else None,
            "feedback_plan_name": feedback_plan.name if feedback_plan else None,
            "feedback_subscription_status": feedback_sub.status if feedback_sub else None,
            "feedback_wa_units_included": int(usage.get("wa_units_included", 0) or 0),
            "feedback_wa_units_used": int(usage.get("wa_units_used", 0) or 0),
            "feedback_wa_units_remaining": int(usage.get("wa_units_remaining", 0) or 0),
        }

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

        user_counts = dict(
            db.execute(
                select(OrganisationMembership.org_id, func.count(func.distinct(OrganisationMembership.user_id)))
                .where(OrganisationMembership.org_id.in_(org_ids))
                .group_by(OrganisationMembership.org_id)
            ).all()
        )

        subs_by_org = AdminOrganisationService._subs_by_org_service(db, org_ids)

        out: list[AdminOrganisationSummary] = []
        for org in org_rows:
            org_subs = subs_by_org.get(org.id, {})
            core_sub = org_subs.get("voxbulk")
            if core_sub is not None:
                core_plan = db.get(Plan, core_sub.plan_id) if core_sub.plan_id else None
                if core_plan is not None and not BillingAccessService.is_valid_core_plan(db, core_plan):
                    core_sub = None
            feedback_sub = org_subs.get("customer_feedback")
            if feedback_sub is not None and str(feedback_sub.status or "").lower() in {"cancelled", "inactive"}:
                feedback_sub = None
            plan_fields = AdminOrganisationService._plan_fields_for_subs(
                db,
                org_id=org.id,
                core_sub=core_sub,
                feedback_sub=feedback_sub,
            )
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
                    wallet_balance_pence=int(getattr(org, "wallet_balance_pence", 0) or 0),
                    **plan_fields,
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

        core_sub = BillingAccessService.get_valid_core_subscription(db, org_id)
        feedback_sub = FeedbackBillingService.get_active_subscription(db, org_id)
        plan_fields = AdminOrganisationService._plan_fields_for_subs(
            db,
            org_id=org_id,
            core_sub=core_sub,
            feedback_sub=feedback_sub,
        )

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
            wallet_balance_pence=int(getattr(org, "wallet_balance_pence", 0) or 0),
            **plan_fields,
        )

    @staticmethod
    def summary_plan_dict(o: AdminOrganisationSummary) -> dict[str, object]:
        return {
            "subscription_status": o.subscription_status,
            "plan_code": o.plan_code,
            "plan_name": o.plan_name,
            "core_plan_code": o.core_plan_code,
            "core_plan_name": o.core_plan_name,
            "core_subscription_status": o.core_subscription_status,
            "feedback_plan_code": o.feedback_plan_code,
            "feedback_plan_name": o.feedback_plan_name,
            "feedback_subscription_status": o.feedback_subscription_status,
            "feedback_wa_units_included": o.feedback_wa_units_included,
            "feedback_wa_units_used": o.feedback_wa_units_used,
            "feedback_wa_units_remaining": o.feedback_wa_units_remaining,
        }
