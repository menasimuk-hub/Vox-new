from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.org_opt_out import OrganisationOptOut
from app.models.organisation import Organisation
from app.services.messaging_log_service import normalize_e164


def _row_dict(r: OrganisationOptOut, *, org_name: str | None = None) -> dict[str, Any]:
    return {
        "id": r.id,
        "org_id": r.org_id,
        "org_name": org_name,
        "phone": r.phone_e164,
        "phone_e164": r.phone_e164,
        "name": r.contact_name,
        "contact_name": r.contact_name,
        "reason": r.reason,
        "created_by_user_id": r.created_by_user_id,
        "created_at": r.created_at,
    }


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
        return [_row_dict(r) for r in rows]

    @staticmethod
    def list_all_admin(
        db: Session,
        *,
        page: int = 1,
        page_size: int = 20,
        org_id: str | None = None,
        phone_q: str | None = None,
        reason_q: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict[str, Any]:
        page = max(1, int(page or 1))
        page_size = min(100, max(1, int(page_size or 20)))
        q = (
            select(OrganisationOptOut, Organisation.name)
            .outerjoin(Organisation, Organisation.id == OrganisationOptOut.org_id)
        )
        count_q = select(func.count()).select_from(OrganisationOptOut)

        if org_id:
            q = q.where(OrganisationOptOut.org_id == str(org_id))
            count_q = count_q.where(OrganisationOptOut.org_id == str(org_id))
        phone = str(phone_q or "").strip()
        if phone:
            like = f"%{phone}%"
            q = q.where(OrganisationOptOut.phone_e164.ilike(like))
            count_q = count_q.where(OrganisationOptOut.phone_e164.ilike(like))
        reason = str(reason_q or "").strip()
        if reason:
            like = f"%{reason}%"
            q = q.where(OrganisationOptOut.reason.ilike(like))
            count_q = count_q.where(OrganisationOptOut.reason.ilike(like))
        if from_date is not None:
            q = q.where(OrganisationOptOut.created_at >= from_date)
            count_q = count_q.where(OrganisationOptOut.created_at >= from_date)
        if to_date is not None:
            q = q.where(OrganisationOptOut.created_at <= to_date)
            count_q = count_q.where(OrganisationOptOut.created_at <= to_date)

        total = int(db.execute(count_q).scalar_one() or 0)
        rows = list(
            db.execute(
                q.order_by(OrganisationOptOut.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        items = [_row_dict(r, org_name=org_name) for r, org_name in rows]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size) if total else 1,
        }

    @staticmethod
    def remove_opt_out_admin(db: Session, *, opt_out_id: str) -> bool:
        row = db.get(OrganisationOptOut, opt_out_id)
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True

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
        return _row_dict(row)

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
