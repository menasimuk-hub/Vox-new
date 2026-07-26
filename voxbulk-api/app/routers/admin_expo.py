"""Admin API — VoxBulk Expo service (industries + local question templates)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.models.expo import ExpoIndustry, ExpoQuestionTemplate
from app.services.expo.booth_service import ExpoBoothService
from app.services.expo.question_bank import list_selectable_questions
from app.services.expo.question_bank import SYSTEM_TEMPLATE_KEYS
from app.services.expo.results_service import ExpoResultsService
from app.services.expo.seed_service import ExpoSeedService

router = APIRouter(prefix="/admin/expo", tags=["admin-expo"])


def _slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return (base or "industry")[:64]


@router.get("/packages")
def list_packages(
    market_zone: str = "gb",
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {"ok": True, "items": ExpoBoothService.list_packages(db, market_zone=market_zone)}


@router.get("/industries")
def list_industries(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"ok": True, "items": ExpoBoothService.list_industries(db)}


@router.post("/industries")
def create_industry(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    slug = _slugify(str(payload.get("slug") or name))
    existing = db.execute(select(ExpoIndustry).where(ExpoIndustry.slug == slug)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Industry slug already exists")
    now = datetime.utcnow()
    row = ExpoIndustry(
        id=str(uuid.uuid4()),
        slug=slug,
        name=name[:128],
        description=(str(payload.get("description") or "").strip() or None),
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
            "slug": row.slug,
            "name": row.name,
            "description": row.description,
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
    row = db.get(ExpoIndustry, industry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Industry not found")
    if "name" in payload:
        row.name = str(payload.get("name") or row.name).strip()[:128]
    if "description" in payload:
        row.description = str(payload.get("description") or "").strip() or None
    if "addon_question" in payload:
        row.addon_question = str(payload.get("addon_question") or "").strip() or None
    if "is_active" in payload:
        row.is_active = bool(payload.get("is_active"))
    if "sort_order" in payload:
        row.sort_order = int(payload.get("sort_order") or row.sort_order)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    return {"ok": True, "item": {"id": row.id, "slug": row.slug, "name": row.name, "addon_question": row.addon_question}}


@router.get("/questions")
def list_questions(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    ExpoSeedService._ensure_question_templates(db)
    db.commit()
    rows = db.execute(select(ExpoQuestionTemplate).order_by(ExpoQuestionTemplate.sort_order.asc())).scalars().all()
    return {
        "ok": True,
        "items": [
            {
                "id": r.id,
                "key": r.question_key,
                "label": r.label,
                "prompt": r.prompt,
                "description": r.description,
                "matches_products": bool(r.matches_products),
                "is_active": bool(r.is_active),
                "sort_order": r.sort_order,
                "is_system": str(r.question_key or "") in SYSTEM_TEMPLATE_KEYS,
            }
            for r in rows
        ],
        "catalog": list_selectable_questions(db),
    }


@router.post("/questions")
def create_question(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    key = _slugify(str(payload.get("key") or payload.get("label") or "")).replace("-", "_")[:64]
    label = str(payload.get("label") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    if not key or not label or not prompt:
        raise HTTPException(status_code=400, detail="key, label and prompt are required")
    existing = db.execute(
        select(ExpoQuestionTemplate).where(ExpoQuestionTemplate.question_key == key)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Question key already exists")
    now = datetime.utcnow()
    row = ExpoQuestionTemplate(
        id=str(uuid.uuid4()),
        question_key=key,
        label=label[:128],
        prompt=prompt[:4000],
        description=(str(payload.get("description") or "").strip() or None),
        matches_products=bool(payload.get("matches_products")),
        is_active=bool(payload.get("is_active", True)),
        sort_order=int(payload.get("sort_order") or 100),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    return {"ok": True, "item": {"id": row.id, "key": row.question_key, "label": row.label, "prompt": row.prompt}}


@router.patch("/questions/{question_id}")
def update_question(
    question_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = db.get(ExpoQuestionTemplate, question_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if "label" in payload:
        row.label = str(payload.get("label") or row.label).strip()[:128]
    if "prompt" in payload:
        row.prompt = str(payload.get("prompt") or row.prompt).strip()[:4000]
    if "description" in payload:
        row.description = str(payload.get("description") or "").strip() or None
    if "matches_products" in payload:
        row.matches_products = bool(payload.get("matches_products"))
    if "is_active" in payload:
        row.is_active = bool(payload.get("is_active"))
    if "sort_order" in payload:
        row.sort_order = int(payload.get("sort_order") or row.sort_order)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    return {"ok": True, "item": {"id": row.id, "key": row.question_key, "label": row.label, "prompt": row.prompt}}


@router.delete("/questions/{question_id}")
def delete_question(question_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    row = db.get(ExpoQuestionTemplate, question_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/seed")
def seed_expo(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    ExpoSeedService.ensure_seeded(db)
    return {"ok": True}


@router.get("/overview")
def overview(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return ExpoResultsService.admin_overview(db)
