"""Custom Org profiles — per-customer WhatsApp workspace admin service.

Phase 1: binds an organisation to its dedicated WhatsApp connection profile,
optional calling profile, and billing plan, and exposes the org's dedicated
industries/templates. Reuses existing services (connection profiles, industries,
plans) rather than duplicating template data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.connection_profile import ConnectionProfile
from app.models.custom_org_profile import (
    STATUS_ACTIVE,
    STATUS_PAUSED,
    STATUS_SETUP,
    CustomOrgProfile,
)
from app.models.industry import Industry
from app.models.industry_organisation import IndustryOrganisation
from app.models.organisation import Organisation
from app.models.plan import Plan

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
            "contact_name": row.contact_name,
            "contact_email": row.contact_email,
            "contact_phone": row.contact_phone,
            "region": row.region,
            "notes": row.notes,
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
        plans = db.execute(select(Plan).order_by(Plan.name)).scalars().all()
        return {
            "wa_profiles": [
                {"id": p.id, "name": p.name, "provider": p.provider, "wa_number": _wa_number(p)}
                for p in wa_profiles
            ],
            "calling_profiles": [{"id": p.id, "name": p.name, "provider": p.provider} for p in voice_profiles],
            "orgs": [{"id": o.id, "name": o.name or o.id} for o in orgs],
            "plans": [{"id": p.id, "name": p.name} for p in plans],
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
        return CustomOrgProfileService._serialize_row(db, row)

    @staticmethod
    def delete_profile(db: Session, profile_id: str) -> None:
        row = db.get(CustomOrgProfile, profile_id)
        if row is None:
            raise CustomOrgProfileError("Profile not found")
        db.delete(row)
        db.commit()
