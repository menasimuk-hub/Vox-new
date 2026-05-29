from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.org_opt_out import OrganisationOptOut
from app.services.messaging_log_service import normalize_e164


class OrgOptOutService:
    @staticmethod
    def list_opt_outs(db: Session, org_id: str) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(OrganisationOptOut)
                .where(OrganisationOptOut.org_id == org_id)
                .order_by(OrganisationOptOut.created_at.desc())
                .limit(500)
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "phone": r.phone_e164,
                "phone_e164": r.phone_e164,
                "name": r.contact_name,
                "contact_name": r.contact_name,
                "reason": r.reason,
                "created_at": r.created_at,
            }
            for r in rows
        ]

    @staticmethod
    def add_opt_out(
        db: Session,
        *,
        org_id: str,
        phone: str,
        contact_name: str | None = None,
        reason: str | None = None,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        phone_e164 = normalize_e164(phone)
        existing = db.execute(
            select(OrganisationOptOut).where(
                OrganisationOptOut.org_id == org_id,
                OrganisationOptOut.phone_e164 == phone_e164,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.contact_name = (contact_name or existing.contact_name or "").strip() or None
            existing.reason = (reason or existing.reason or "").strip() or None
            db.add(existing)
            db.commit()
            db.refresh(existing)
            row = existing
        else:
            row = OrganisationOptOut(
                org_id=org_id,
                phone_e164=phone_e164,
                contact_name=(contact_name or "").strip() or None,
                reason=(reason or "").strip() or None,
                created_by_user_id=created_by_user_id,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return {
            "id": row.id,
            "phone": row.phone_e164,
            "phone_e164": row.phone_e164,
            "name": row.contact_name,
            "contact_name": row.contact_name,
            "reason": row.reason,
            "created_at": row.created_at,
        }

    @staticmethod
    def remove_opt_out(db: Session, *, org_id: str, opt_out_id: str) -> bool:
        row = db.execute(
            select(OrganisationOptOut).where(
                OrganisationOptOut.id == opt_out_id,
                OrganisationOptOut.org_id == org_id,
            )
        ).scalar_one_or_none()
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True

    @staticmethod
    def is_phone_opted_out(db: Session, org_id: str, phone: str) -> bool:
        raw = str(phone or "").strip()
        if not raw:
            return False
        try:
            phone_e164 = normalize_e164(raw)
        except ValueError:
            return False
        hit = db.execute(
            select(OrganisationOptOut.id).where(
                OrganisationOptOut.org_id == org_id,
                OrganisationOptOut.phone_e164 == phone_e164,
            )
        ).scalar_one_or_none()
        return hit is not None
