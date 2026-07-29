"""Returning Expo visitor identity — skip business card on later scans at same exhibition."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoExhibition, ExpoVisitorIdentity


class ExpoVisitorIdentityService:
    @staticmethod
    def _expires_for_exhibition(db: Session, exhibition: ExpoExhibition, booth: ExpoBooth | None = None) -> datetime:
        if exhibition.ends_on is not None:
            return exhibition.ends_on
        if booth is not None and booth.expires_at is not None:
            return booth.expires_at
        # Fallback: 7 days from now
        from datetime import timedelta

        return datetime.utcnow() + timedelta(days=7)

    @staticmethod
    def lookup(
        db: Session,
        *,
        exhibition_id: str,
        visitor_token: str | None = None,
        visitor_phone: str | None = None,
        visitor_email: str | None = None,
    ) -> ExpoVisitorIdentity | None:
        now = datetime.utcnow()
        if visitor_token:
            row = db.execute(
                select(ExpoVisitorIdentity).where(
                    ExpoVisitorIdentity.exhibition_id == exhibition_id,
                    ExpoVisitorIdentity.visitor_token == visitor_token.strip(),
                    ExpoVisitorIdentity.expires_at > now,
                )
            ).scalar_one_or_none()
            if row:
                return row
        clauses = []
        phone = (visitor_phone or "").strip()
        email = (visitor_email or "").strip().lower()
        if phone and not phone.startswith("web-pending") and not phone.startswith("web:"):
            clauses.append(ExpoVisitorIdentity.visitor_phone == phone)
        if email and "@" in email and not email.endswith("@expo.local"):
            clauses.append(ExpoVisitorIdentity.visitor_email == email)
        if not clauses:
            return None
        return db.execute(
            select(ExpoVisitorIdentity)
            .where(
                ExpoVisitorIdentity.exhibition_id == exhibition_id,
                ExpoVisitorIdentity.expires_at > now,
                or_(*clauses),
            )
            .order_by(ExpoVisitorIdentity.updated_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def upsert(
        db: Session,
        *,
        org_id: str,
        exhibition_id: str,
        booth: ExpoBooth | None,
        visitor_token: str | None,
        visitor_phone: str | None,
        visitor_email: str | None,
        name: str | None,
        company: str | None,
    ) -> ExpoVisitorIdentity | None:
        exhibition = db.get(ExpoExhibition, exhibition_id)
        if exhibition is None:
            return None
        phone = (visitor_phone or "").strip() or None
        email = (visitor_email or "").strip().lower() or None
        if email and email.endswith("@expo.local"):
            email = None
        if phone and (phone.startswith("web-pending") or phone.startswith("web:")):
            # Keep web UUID phones as identity keys
            pass
        token = (visitor_token or "").strip() or None
        if not token:
            token = str(uuid.uuid4())
        existing = ExpoVisitorIdentityService.lookup(
            db,
            exhibition_id=exhibition_id,
            visitor_token=token,
            visitor_phone=phone,
            visitor_email=email,
        )
        now = datetime.utcnow()
        expires = ExpoVisitorIdentityService._expires_for_exhibition(db, exhibition, booth)
        if existing is None:
            existing = ExpoVisitorIdentity(
                id=str(uuid.uuid4()),
                org_id=org_id,
                exhibition_id=exhibition_id,
                visitor_token=token,
                visitor_phone=phone,
                visitor_email=email,
                name=(name or "").strip() or None,
                company=(company or "").strip() or None,
                expires_at=expires,
                created_at=now,
                updated_at=now,
            )
            db.add(existing)
        else:
            if phone:
                existing.visitor_phone = phone
            if email:
                existing.visitor_email = email
            if name:
                existing.name = name.strip()
            if company:
                existing.company = company.strip()
            existing.visitor_token = token or existing.visitor_token
            existing.expires_at = expires
            existing.updated_at = now
            db.add(existing)
        db.flush()
        return existing

    @staticmethod
    def to_public(row: ExpoVisitorIdentity) -> dict[str, Any]:
        return {
            "visitor_token": row.visitor_token,
            "name": row.name,
            "company": row.company,
            "visitor_email": row.visitor_email,
            "visitor_phone": row.visitor_phone,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }

    @staticmethod
    def purge_expired(db: Session) -> int:
        now = datetime.utcnow()
        result = db.execute(delete(ExpoVisitorIdentity).where(ExpoVisitorIdentity.expires_at <= now))
        db.commit()
        return int(result.rowcount or 0)
