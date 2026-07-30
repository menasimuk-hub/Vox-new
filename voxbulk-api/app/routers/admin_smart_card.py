"""Admin API — Smart Card QR questions, mailbox, seed, overview."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.models.smart_card import (
    SmartCardCompany,
    SmartCardLead,
    SmartCardQuestionTemplate,
    SmartCardRepresentative,
    SmartCardSession,
)
from app.services.smart_card.mailbox_settings_service import SmartCardMailboxSettingsService
from app.services.smart_card.seed_service import SmartCardSeedService

router = APIRouter(prefix="/admin/smart-card", tags=["admin-smart-card"])


@router.post("/seed")
def seed(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    SmartCardSeedService.ensure_seeded(db)
    return {"ok": True}


@router.get("/overview")
def overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    companies = int(db.execute(select(func.count()).select_from(SmartCardCompany)).scalar() or 0)
    reps = int(db.execute(select(func.count()).select_from(SmartCardRepresentative)).scalar() or 0)
    leads = int(db.execute(select(func.count()).select_from(SmartCardLead)).scalar() or 0)
    sessions = int(db.execute(select(func.count()).select_from(SmartCardSession)).scalar() or 0)
    return {
        "ok": True,
        "companies": companies,
        "representatives": reps,
        "leads": leads,
        "sessions": sessions,
    }


@router.get("/questions")
def list_questions(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    rows = (
        db.execute(select(SmartCardQuestionTemplate).order_by(SmartCardQuestionTemplate.sort_order.asc()))
        .scalars()
        .all()
    )
    return {
        "ok": True,
        "items": [
            {
                "id": r.id,
                "question_key": r.question_key,
                "label": r.label,
                "prompt": r.prompt,
                "description": r.description,
                "kind": r.kind,
                "is_active": bool(r.is_active),
                "sort_order": r.sort_order,
            }
            for r in rows
        ],
    }


@router.patch("/questions/{question_key}")
def patch_question(
    question_key: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = db.execute(
        select(SmartCardQuestionTemplate).where(SmartCardQuestionTemplate.question_key == question_key)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if "label" in payload:
        row.label = str(payload.get("label") or row.label)[:128]
    if "prompt" in payload:
        row.prompt = str(payload.get("prompt") or row.prompt)
    if "description" in payload:
        row.description = str(payload.get("description") or "") or None
    if "is_active" in payload:
        row.is_active = bool(payload.get("is_active"))
    if "sort_order" in payload:
        try:
            row.sort_order = int(payload.get("sort_order"))
        except (TypeError, ValueError):
            pass
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    return {"ok": True}


@router.get("/mailbox")
def get_mailbox(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"ok": True, **SmartCardMailboxSettingsService.to_public_dict(db)}


@router.put("/mailbox")
def put_mailbox(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    SmartCardMailboxSettingsService.upsert(
        db,
        mailbox_email=str(payload.get("mailbox_email") or "smartqr@voxbulk.com"),
        from_name=str(payload.get("from_name") or "VOXBULK Smart Card QR"),
        smtp_username=payload.get("smtp_username"),
        is_enabled=bool(payload.get("is_enabled", True)),
        password=payload.get("password"),
    )
    return {"ok": True, **SmartCardMailboxSettingsService.to_public_dict(db)}
