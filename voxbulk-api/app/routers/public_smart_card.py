"""Public Smart Card QR landing + session stubs (live / preview / expired)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.smart_card import SmartCardRepresentative
from app.services.smart_card.company_service import SmartCardCompanyService, SmartCardEntitlementService

router = APIRouter(prefix="/public/smart-card", tags=["public-smart-card"])


@router.get("/{token}")
def get_card(token: str, db: Session = Depends(get_db)):
    rep = db.execute(
        select(SmartCardRepresentative).where(SmartCardRepresentative.qr_token == token)
    ).scalar_one_or_none()
    if rep is None or str(rep.status or "") != "active":
        raise HTTPException(status_code=404, detail="Smart Card QR not found")

    company = SmartCardCompanyService.get_or_create(db, rep.org_id)
    mode = SmartCardEntitlementService.access_mode(db, rep.org_id)
    renew_url = "https://dashboard.voxbulk.com/account/smart-card/packages"

    if mode == "expired":
        return {
            "ok": True,
            "status": "expired",
            "message": (
                "We're sorry — this Smart Card QR account has expired. "
                "Please ask the company to renew their package."
            ),
            "renew_url": renew_url,
            "representative": {"name": rep.name},
            "company": {"name": company.name},
        }

    if mode == "preview_exhausted":
        return {
            "ok": True,
            "status": "preview_exhausted",
            "message": (
                "Preview tests are used up (15). "
                "This Smart Card QR will go live after the organisation buys or renews a package."
            ),
            "renew_url": renew_url,
            "representative": {"name": rep.name},
            "company": {"name": company.name},
        }

    return {
        "ok": True,
        "status": mode,  # live | preview
        "preview_tests_remaining": max(
            0, 15 - int(company.preview_tests_used or 0)
        )
        if mode == "preview"
        else None,
        "representative": {
            "id": rep.id,
            "name": rep.name,
            "email": rep.email,
            "website": rep.website,
            "mobile": rep.mobile,
            "landline": rep.landline,
            "extension": rep.extension,
        },
        "company": {
            "name": company.name,
            "website": company.website,
            "description": company.description,
        },
        "qr_token": rep.qr_token,
    }
