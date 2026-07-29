"""Org-level Expo profile defaults (contact email + representatives)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.expo import ExpoOrgProfile
from app.services.expo.question_bank import parse_representative_contacts


class ExpoOrgProfileService:
    @staticmethod
    def get(db: Session, org_id: str) -> dict[str, Any]:
        row = db.get(ExpoOrgProfile, org_id)
        if row is None:
            return {
                "visitor_contact_email": None,
                "representatives": [],
                "company_website": None,
                "notify_mobile": None,
            }
        return {
            "visitor_contact_email": row.visitor_contact_email,
            "representatives": parse_representative_contacts(row.representatives_json),
            "company_website": row.company_website,
            "notify_mobile": row.notify_mobile,
        }

    @staticmethod
    def save(
        db: Session,
        *,
        org_id: str,
        visitor_contact_email: str | None,
        representatives: list[dict[str, Any]] | None,
        company_website: str | None,
        notify_mobile: str | None,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        row = db.get(ExpoOrgProfile, org_id)
        if row is None:
            row = ExpoOrgProfile(org_id=org_id, created_at=now, updated_at=now)
            db.add(row)
        email = (visitor_contact_email or "").strip().lower() or None
        if email and "@" not in email:
            email = None
        row.visitor_contact_email = email
        row.representatives_json = json.dumps(representatives) if representatives else None
        row.company_website = (company_website or "").strip()[:512] or None
        row.notify_mobile = (notify_mobile or "").strip()[:64] or None
        row.updated_at = now
        db.add(row)
        db.flush()
        return ExpoOrgProfileService.get(db, org_id)
