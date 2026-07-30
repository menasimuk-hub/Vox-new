"""Admin API — Smart Card QR questions, industries, mailbox, seed, overview."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.models.smart_card import (
    SmartCardCompany,
    SmartCardIndustry,
    SmartCardLead,
    SmartCardQuestionTemplate,
    SmartCardRepresentative,
    SmartCardSession,
)
from app.services.smart_card.mailbox_settings_service import SmartCardMailboxSettingsService
from app.services.smart_card.seed_service import SmartCardSeedService
from app.services.smtp_mailer_service import SmtpMailerError

router = APIRouter(prefix="/admin/smart-card", tags=["admin-smart-card"])


def _slugify_key(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
    return (base or "question")[:64]


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


@router.get("/industries")
def list_industries(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    rows = (
        db.execute(select(SmartCardIndustry).order_by(SmartCardIndustry.sort_order.asc(), SmartCardIndustry.name.asc()))
        .scalars()
        .all()
    )
    return {
        "ok": True,
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "addon_question": r.addon_question,
                "is_active": bool(r.is_active),
                "sort_order": r.sort_order,
            }
            for r in rows
        ],
    }


@router.post("/industries")
def create_industry(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    existing = db.execute(select(SmartCardIndustry).where(SmartCardIndustry.name == name)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Industry name already exists")
    now = datetime.utcnow()
    row = SmartCardIndustry(
        id=str(uuid.uuid4()),
        name=name[:128],
        addon_question=(str(payload.get("addon_question") or "").strip() or None),
        is_active=bool(payload.get("is_active", True)),
        sort_order=int(payload.get("sort_order") or 100),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    return {
        "ok": True,
        "item": {
            "id": row.id,
            "name": row.name,
            "addon_question": row.addon_question,
            "is_active": row.is_active,
            "sort_order": row.sort_order,
        },
    }


@router.patch("/industries/{industry_id}")
def update_industry(
    industry_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = db.get(SmartCardIndustry, industry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Industry not found")
    if "name" in payload:
        row.name = str(payload.get("name") or row.name).strip()[:128]
    if "addon_question" in payload:
        row.addon_question = str(payload.get("addon_question") or "").strip() or None
    if "is_active" in payload:
        row.is_active = bool(payload.get("is_active"))
    if "sort_order" in payload:
        try:
            row.sort_order = int(payload.get("sort_order") or row.sort_order)
        except (TypeError, ValueError):
            pass
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    return {
        "ok": True,
        "item": {
            "id": row.id,
            "name": row.name,
            "addon_question": row.addon_question,
            "is_active": row.is_active,
            "sort_order": row.sort_order,
        },
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
                "key": r.question_key,
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


@router.post("/questions")
def create_question(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    key = _slugify_key(str(payload.get("key") or payload.get("question_key") or payload.get("label") or ""))
    label = str(payload.get("label") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    if not key or not label or not prompt:
        raise HTTPException(status_code=400, detail="key, label and prompt are required")
    existing = db.execute(
        select(SmartCardQuestionTemplate).where(SmartCardQuestionTemplate.question_key == key)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Question key already exists")
    now = datetime.utcnow()
    row = SmartCardQuestionTemplate(
        id=str(uuid.uuid4()),
        question_key=key,
        label=label[:128],
        prompt=prompt[:4000],
        description=(str(payload.get("description") or "").strip() or None),
        kind=str(payload.get("kind") or "selectable")[:32],
        is_active=bool(payload.get("is_active", True)),
        sort_order=int(payload.get("sort_order") or 100),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    return {
        "ok": True,
        "item": {
            "id": row.id,
            "question_key": row.question_key,
            "key": row.question_key,
            "label": row.label,
            "prompt": row.prompt,
        },
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
        # Allow patch by id as well (Expo-style clients).
        row = db.get(SmartCardQuestionTemplate, question_key)
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


@router.delete("/questions/{question_id}")
def delete_question(question_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    row = db.get(SmartCardQuestionTemplate, question_id)
    if row is None:
        row = db.execute(
            select(SmartCardQuestionTemplate).where(SmartCardQuestionTemplate.question_key == question_id)
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Question not found")
    # Soft-deactivate system-ish keys; hard-delete custom selectable ones.
    if str(row.kind or "") == "system":
        row.is_active = False
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        return {"ok": True, "deactivated": True}
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/mailbox")
def get_mailbox(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"ok": True, **SmartCardMailboxSettingsService.to_public_dict(db)}


@router.put("/mailbox")
def put_mailbox(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    smtp_port = payload.get("smtp_port")
    try:
        smtp_port_int = int(smtp_port) if smtp_port not in (None, "") else None
    except (TypeError, ValueError):
        smtp_port_int = None
    imap_port = payload.get("imap_port", 993)
    try:
        imap_port_int = int(imap_port) if imap_port not in (None, "") else 993
    except (TypeError, ValueError):
        imap_port_int = 993

    SmartCardMailboxSettingsService.upsert(
        db,
        mailbox_email=str(payload.get("mailbox_email") or "smartqr@voxbulk.com"),
        from_name=str(payload.get("from_name") or "VOXBULK Smart Card QR"),
        smtp_username=payload.get("smtp_username"),
        smtp_host=payload.get("smtp_host"),
        smtp_port=smtp_port_int,
        is_enabled=bool(payload.get("is_enabled", True)),
        password=payload.get("password"),
        imap_host=payload.get("imap_host"),
        imap_port=imap_port_int,
        imap_use_ssl=bool(payload.get("imap_use_ssl", True)) if "imap_use_ssl" in payload else None,
        imap_use_tls=bool(payload.get("imap_use_tls", False)) if "imap_use_tls" in payload else None,
        imap_username=payload.get("imap_username"),
        imap_password=payload.get("imap_password"),
    )
    return {"ok": True, **SmartCardMailboxSettingsService.to_public_dict(db)}


@router.post("/mailbox/test-send")
def post_mailbox_test_send(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.smart_card.mailbox_sync_service import test_smtp_send

    to_email = str(payload.get("to_email") or payload.get("to") or "").strip()
    try:
        result = test_smtp_send(db, to_email=to_email)
    except SmtpMailerError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result


@router.post("/mailbox/test-imap")
def post_mailbox_test_imap(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.smart_card.mailbox_sync_service import test_imap

    result = test_imap(db)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("detail") or "IMAP test failed")
    return result


@router.post("/mailbox/sync-now")
def post_mailbox_sync_now(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    from app.services.smart_card.mailbox_sync_service import sync_to_tickets

    result = sync_to_tickets(db)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "Sync failed")
    return result
