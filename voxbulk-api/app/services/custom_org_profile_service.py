"""Custom Org profiles — per-customer WhatsApp workspace admin service.

Phase 1: binds an organisation to its dedicated WhatsApp connection profile,
optional calling profile, and billing plan, and exposes the org's dedicated
industries/templates. Reuses existing services (connection profiles, industries,
plans) rather than duplicating template data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.connection_profile import ConnectionProfile, ConnectionProfileOrg, ConnectionProfileService
from app.models.custom_org_profile import (
    STATUS_ACTIVE,
    STATUS_PAUSED,
    STATUS_SETUP,
    CustomOrgProfile,
)
from app.models.industry import Industry
from app.models.industry_organisation import IndustryOrganisation
from app.models.organisation import Organisation
from app.models.customer_feedback import FeedbackPackage
from app.models.plan import Plan
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.connection.constants import SERVICE_CUSTOMER_FEEDBACK, SERVICE_SURVEY
from app.services.industry_service import IndustryService
from app.services.products_hub_service import ProductsHubService
from app.services.survey_industry_scope import resolve_dedicated_org_id_for_industry

_VALID_STATUS = {STATUS_SETUP, STATUS_ACTIVE, STATUS_PAUSED}


class CustomOrgProfileError(Exception):
    pass


def _wa_number(profile: ConnectionProfile | None) -> str | None:
    if profile is None:
        return None
    if (profile.provider or "").lower() == "telnyx":
        return profile.telnyx_number or profile.meta_whatsapp_from
    return profile.meta_whatsapp_from or profile.telnyx_number


class CustomOrgProfileService:
    @staticmethod
    def _next_internal_ref(db: Session) -> str:
        count = db.execute(select(func.count(CustomOrgProfile.id))).scalar() or 0
        return f"WAP-{count + 1:04d}"

    @staticmethod
    def _plan_display_fields(db: Session, plan: Plan | None) -> dict[str, Any]:
        empty = {
            "plan_code": None,
            "plan_service": None,
            "plan_currency": None,
            "plan_region": None,
            "plan_price_display": None,
        }
        if plan is None:
            return empty
        fb_pkg = None
        if ProductsHubService.product_line_for_plan(plan) == "customer_feedback":
            fb_pkg = db.execute(
                select(FeedbackPackage).where(FeedbackPackage.plan_id == plan.id)
            ).scalar_one_or_none()
        enriched = ProductsHubService.enrich_plan_row(db, plan, fb_pkg=fb_pkg)
        if enriched is None:
            return {**empty, "plan_code": plan.code}
        return {
            "plan_code": plan.code,
            "plan_service": enriched.get("group_label"),
            "plan_currency": enriched.get("currency"),
            "plan_region": enriched.get("region"),
            "plan_price_display": enriched.get("price_display"),
        }

    @staticmethod
    def _org_industry_ids(db: Session, org_id: str | None) -> list[str]:
        if not org_id:
            return []
        return [
            str(x)
            for x in db.execute(
                select(IndustryOrganisation.industry_id).where(IndustryOrganisation.org_id == org_id)
            ).scalars().all()
        ]

    @staticmethod
    def _serialize_row(db: Session, row: CustomOrgProfile) -> dict[str, Any]:
        wa = db.get(ConnectionProfile, row.wa_profile_id) if row.wa_profile_id else None
        calling = db.get(ConnectionProfile, row.calling_profile_id) if row.calling_profile_id else None
        org = db.get(Organisation, row.org_id) if row.org_id else None
        plan = db.get(Plan, row.plan_id) if row.plan_id else None

        industry_ids = CustomOrgProfileService._org_industry_ids(db, row.org_id)
        industries = []
        if industry_ids:
            rows = db.execute(
                select(Industry).where(Industry.id.in_(industry_ids))
            ).scalars().all()
            industries = [{"id": i.id, "name": i.name, "slug": getattr(i, "slug", None)} for i in rows]

        return {
            "id": row.id,
            "name": row.name,
            "internal_ref": row.internal_ref,
            "status": row.status,
            "org_id": row.org_id,
            "org_name": (org.name if org else None),
            "wa_profile_id": row.wa_profile_id,
            "wa_profile_name": (wa.name if wa else None),
            "wa_provider": (wa.provider if wa else None),
            "wa_number": _wa_number(wa),
            "calling_profile_id": row.calling_profile_id,
            "calling_profile_name": (calling.name if calling else None),
            "plan_id": row.plan_id,
            "plan_name": (plan.name if plan else None),
            **CustomOrgProfileService._plan_display_fields(db, plan),
            "contact_name": row.contact_name,
            "contact_email": row.contact_email,
            "contact_phone": row.contact_phone,
            "region": row.region,
            "notes": row.notes,
            "survey_enabled": bool(getattr(row, "survey_enabled", True)),
            "feedback_enabled": bool(getattr(row, "feedback_enabled", False)),
            "industries": industries,
            "industry_count": len(industries),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def list_profiles(db: Session) -> list[dict[str, Any]]:
        rows = db.execute(
            select(CustomOrgProfile).order_by(CustomOrgProfile.created_at.desc())
        ).scalars().all()
        return [CustomOrgProfileService._serialize_row(db, r) for r in rows]

    @staticmethod
    def options(db: Session) -> dict[str, Any]:
        wa_profiles = db.execute(
            select(ConnectionProfile).where(ConnectionProfile.channel == "whatsapp").order_by(ConnectionProfile.name)
        ).scalars().all()
        voice_profiles = db.execute(
            select(ConnectionProfile).where(ConnectionProfile.channel == "voice").order_by(ConnectionProfile.name)
        ).scalars().all()
        orgs = db.execute(select(Organisation).order_by(Organisation.name)).scalars().all()
        plans = ProductsHubService.list_assignable_plans(db)
        return {
            "wa_profiles": [
                {"id": p.id, "name": p.name, "provider": p.provider, "wa_number": _wa_number(p)}
                for p in wa_profiles
            ],
            "calling_profiles": [{"id": p.id, "name": p.name, "provider": p.provider} for p in voice_profiles],
            "orgs": [{"id": o.id, "name": o.name or o.id} for o in orgs],
            "plans": plans,
        }

    @staticmethod
    def get_profile(db: Session, profile_id: str) -> dict[str, Any] | None:
        row = db.get(CustomOrgProfile, profile_id)
        if row is None:
            return None
        return CustomOrgProfileService._serialize_row(db, row)

    @staticmethod
    def _apply_payload(row: CustomOrgProfile, payload: dict[str, Any]) -> None:
        def _s(key: str) -> str | None:
            if key not in payload:
                return getattr(row, key)
            v = payload.get(key)
            v = str(v).strip() if v is not None else None
            return v or None

        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise CustomOrgProfileError("Profile / Org name is required")
            row.name = name
        row.org_id = _s("org_id")
        row.wa_profile_id = _s("wa_profile_id")
        row.calling_profile_id = _s("calling_profile_id")
        row.plan_id = _s("plan_id")
        row.contact_name = _s("contact_name")
        row.contact_email = _s("contact_email")
        row.contact_phone = _s("contact_phone")
        row.region = _s("region")
        if "notes" in payload:
            notes = payload.get("notes")
            row.notes = (str(notes).strip() or None) if notes is not None else None
        if "status" in payload:
            st = str(payload.get("status") or STATUS_SETUP).strip().lower()
            if st not in _VALID_STATUS:
                raise CustomOrgProfileError(f"Invalid status: {st}")
            row.status = st
        if "survey_enabled" in payload:
            row.survey_enabled = bool(payload.get("survey_enabled"))
        if "feedback_enabled" in payload:
            row.feedback_enabled = bool(payload.get("feedback_enabled"))

    @staticmethod
    def _ensure_org_on_profile(db: Session, profile_id: str | None, org_id: str | None) -> None:
        if not profile_id or not org_id:
            return
        exists = db.execute(
            select(ConnectionProfileOrg).where(
                ConnectionProfileOrg.profile_id == profile_id,
                ConnectionProfileOrg.org_id == org_id,
            )
        ).scalar_one_or_none()
        if exists is not None:
            return
        db.add(
            ConnectionProfileOrg(
                profile_id=profile_id,
                org_id=org_id,
            )
        )

    @staticmethod
    def _sync_connection_profile_services(
        db: Session,
        profile_id: str | None,
        *,
        survey_enabled: bool,
        feedback_enabled: bool,
    ) -> None:
        if not profile_id:
            return
        services: dict[str, bool] = {}
        if survey_enabled:
            services[SERVICE_SURVEY] = True
        if feedback_enabled:
            services[SERVICE_CUSTOMER_FEEDBACK] = True
        if not services:
            return
        existing = {
            svc.service_code: svc
            for svc in db.execute(
                select(ConnectionProfileService).where(ConnectionProfileService.profile_id == profile_id)
            ).scalars().all()
        }
        now = datetime.utcnow()
        for code, enabled in services.items():
            row = existing.get(code)
            if row is None:
                db.add(
                    ConnectionProfileService(
                        profile_id=profile_id,
                        service_code=code,
                        enabled=bool(enabled),
                        created_at=now,
                        updated_at=now,
                    )
                )
            elif not row.enabled and enabled:
                row.enabled = True
                row.updated_at = now
                db.add(row)

    @staticmethod
    def _sync_org_service_grants(
        db: Session,
        org_id: str | None,
        *,
        survey_enabled: bool,
        feedback_enabled: bool,
    ) -> None:
        if not org_id:
            return
        org = db.get(Organisation, org_id)
        if org is None:
            return
        from app.services.org_enabled_services import parse_enabled_services, serialize_enabled_services

        allowed = parse_enabled_services(org.allowed_services_json)
        allowed["survey"] = bool(survey_enabled)
        allowed["customer_feedback"] = bool(feedback_enabled)
        org.allowed_services_json = serialize_enabled_services(allowed)

        enabled = parse_enabled_services(org.enabled_services_json)
        if survey_enabled:
            enabled["survey"] = True
        if feedback_enabled:
            enabled["customer_feedback"] = True
        enabled = {key: bool(allowed.get(key)) and bool(enabled.get(key)) for key in allowed}
        if not any(enabled.values()):
            enabled = dict(allowed)
        org.enabled_services_json = serialize_enabled_services(enabled)
        db.add(org)

    @staticmethod
    def _stamp_org_owned_templates(db: Session, org_id: str | None) -> None:
        if not org_id:
            return
        for industry_id in CustomOrgProfileService._org_industry_ids(db, org_id):
            dedicated = resolve_dedicated_org_id_for_industry(db, industry_id)
            if dedicated != org_id:
                continue
            db.execute(
                update(TelnyxWhatsappTemplate)
                .where(TelnyxWhatsappTemplate.industry_id == industry_id)
                .where(TelnyxWhatsappTemplate.org_id.is_(None))
                .values(org_id=org_id)
            )

    @staticmethod
    def _apply_runtime_bindings(db: Session, row: CustomOrgProfile) -> None:
        org_id = str(row.org_id or "").strip() or None
        if not org_id:
            return
        CustomOrgProfileService._ensure_org_on_profile(db, row.wa_profile_id, org_id)
        CustomOrgProfileService._ensure_org_on_profile(db, row.calling_profile_id, org_id)
        CustomOrgProfileService._sync_connection_profile_services(
            db,
            row.wa_profile_id,
            survey_enabled=bool(getattr(row, "survey_enabled", True)),
            feedback_enabled=bool(getattr(row, "feedback_enabled", False)),
        )
        CustomOrgProfileService._sync_org_service_grants(
            db,
            org_id,
            survey_enabled=bool(getattr(row, "survey_enabled", True)),
            feedback_enabled=bool(getattr(row, "feedback_enabled", False)),
        )
        CustomOrgProfileService._stamp_org_owned_templates(db, org_id)

    @staticmethod
    def resolve_plan_for_org(db: Session, org_id: str) -> Plan | None:
        row = (
            db.execute(
                select(CustomOrgProfile)
                .where(CustomOrgProfile.org_id == org_id)
                .where(CustomOrgProfile.status == STATUS_ACTIVE)
                .where(CustomOrgProfile.plan_id.isnot(None))
                .order_by(CustomOrgProfile.updated_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row is None or not row.plan_id:
            return None
        return db.get(Plan, row.plan_id)

    @staticmethod
    def create_profile(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        name = str((payload or {}).get("name") or "").strip()
        if not name:
            raise CustomOrgProfileError("Profile / Org name is required")
        row = CustomOrgProfile(name=name, status=STATUS_SETUP)
        row.internal_ref = CustomOrgProfileService._next_internal_ref(db)
        CustomOrgProfileService._apply_payload(row, payload or {})
        db.add(row)
        db.commit()
        db.refresh(row)
        CustomOrgProfileService._apply_runtime_bindings(db, row)
        db.commit()
        db.refresh(row)
        return CustomOrgProfileService._serialize_row(db, row)

    @staticmethod
    def update_profile(db: Session, profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = db.get(CustomOrgProfile, profile_id)
        if row is None:
            raise CustomOrgProfileError("Profile not found")
        CustomOrgProfileService._apply_payload(row, payload or {})
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        CustomOrgProfileService._apply_runtime_bindings(db, row)
        db.commit()
        db.refresh(row)
        return CustomOrgProfileService._serialize_row(db, row)

    @staticmethod
    def delete_profile(db: Session, profile_id: str) -> None:
        row = db.get(CustomOrgProfile, profile_id)
        if row is None:
            raise CustomOrgProfileError("Profile not found")
        db.delete(row)
        db.commit()
