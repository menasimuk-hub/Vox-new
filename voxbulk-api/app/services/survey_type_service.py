"""Survey Type CRUD and default seed data for WA Survey admin."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_type_template_service import SurveyTypeTemplateService

DEFAULT_SURVEY_TYPES: list[dict[str, Any]] = [
    {
        "slug": "customer_satisfaction",
        "name": "Customer satisfaction",
        "description": "Measure overall satisfaction and likelihood to recommend.",
        "sort_order": 10,
    },
    {
        "slug": "service_quality",
        "name": "Service quality",
        "description": "Collect feedback on service delivery and staff experience.",
        "sort_order": 20,
    },
    {
        "slug": "price_value",
        "name": "Price / value feedback",
        "description": "Understand perceived value and pricing sentiment.",
        "sort_order": 30,
    },
    {
        "slug": "complaint_followup",
        "name": "Complaint follow-up",
        "description": "Follow up after a complaint to confirm resolution.",
        "sort_order": 40,
    },
    {
        "slug": "quick_feedback",
        "name": "Quick feedback",
        "description": "Short pulse survey for fast feedback loops.",
        "sort_order": 50,
    },
]

LENGTH_OPTIONS = {
    "short": 4,
    "standard": 5,
    "detailed": 6,
}


def survey_type_to_dict(row: SurveyType, *, template_counts: dict[str, int] | None = None) -> dict[str, Any]:
    counts = template_counts or {}
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "is_active": bool(row.is_active),
        "default_length": row.default_length,
        "min_length": int(row.min_length or 4),
        "max_length": int(row.max_length or 6),
        "supports_anonymous": bool(row.supports_anonymous),
        "sort_order": int(row.sort_order or 100),
        "standard_template_count": int(counts.get("standard") or 0),
        "anonymous_template_count": int(counts.get("anonymous") or 0),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class SurveyTypeService:
    @staticmethod
    def ensure_defaults(db: Session) -> None:
        now = datetime.utcnow()
        for item in DEFAULT_SURVEY_TYPES:
            existing = db.execute(select(SurveyType).where(SurveyType.slug == item["slug"])).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                SurveyType(
                    id=str(uuid.uuid4()),
                    slug=item["slug"],
                    name=item["name"],
                    description=item.get("description"),
                    is_active=True,
                    default_length="standard",
                    min_length=4,
                    max_length=6,
                    supports_anonymous=True,
                    sort_order=int(item.get("sort_order") or 100),
                    created_at=now,
                    updated_at=now,
                )
            )
        db.commit()

    @staticmethod
    def _template_counts(db: Session, survey_type_id: str) -> dict[str, int]:
        return SurveyTypeTemplateService.template_counts_for_survey_type(db, survey_type_id)

    @staticmethod
    def _linked_template_ids(db: Session, survey_type_id: str) -> list[int]:
        return [m.template_id for m in SurveyTypeTemplateService.list_for_survey_type(db, survey_type_id)]

    @staticmethod
    def list_types(db: Session) -> list[dict[str, Any]]:
        SurveyTypeService.ensure_defaults(db)
        rows = list(db.execute(select(SurveyType).order_by(SurveyType.sort_order.asc(), SurveyType.name.asc())).scalars())
        payload: list[dict[str, Any]] = []
        for row in rows:
            counts = SurveyTypeService._template_counts(db, row.id)
            data = survey_type_to_dict(row, template_counts=counts)
            linked_ids = SurveyTypeService._linked_template_ids(db, row.id)
            if linked_ids:
                last_sync = db.execute(
                    select(func.max(TelnyxWhatsappTemplate.synced_at)).where(
                        TelnyxWhatsappTemplate.id.in_(linked_ids)
                    )
                ).scalar_one_or_none()
            else:
                last_sync = None
            data["last_synced_at"] = last_sync.isoformat() if last_sync else None
            if linked_ids:
                approved = db.execute(
                    select(func.count())
                    .select_from(TelnyxWhatsappTemplate)
                    .where(
                        TelnyxWhatsappTemplate.id.in_(linked_ids),
                        func.upper(TelnyxWhatsappTemplate.status) == "APPROVED",
                    )
                ).scalar_one()
                pending = db.execute(
                    select(func.count())
                    .select_from(TelnyxWhatsappTemplate)
                    .where(
                        TelnyxWhatsappTemplate.id.in_(linked_ids),
                        func.upper(TelnyxWhatsappTemplate.status).in_(("PENDING", "DRAFT", "UNKNOWN", "LOCAL_DRAFT")),
                    )
                ).scalar_one()
            else:
                approved = pending = 0
            if int(approved or 0) > 0:
                data["status_label"] = "Ready"
            elif int(pending or 0) > 0:
                data["status_label"] = "Pending approval"
            else:
                data["status_label"] = "Needs templates"
            payload.append(data)
        return payload

    @staticmethod
    def get_type(db: Session, type_id: str) -> SurveyType | None:
        tid = str(type_id or "").strip()
        if not tid:
            return None
        return db.get(SurveyType, tid)

    @staticmethod
    def get_by_slug(db: Session, slug: str) -> SurveyType | None:
        key = str(slug or "").strip().lower()
        if not key:
            return None
        return db.execute(select(SurveyType).where(SurveyType.slug == key)).scalar_one_or_none()

    @staticmethod
    def create_type(db: Session, payload: dict[str, Any]) -> SurveyType:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Survey type name is required")
        slug_raw = str(payload.get("slug") or name).strip().lower()
        slug = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in slug_raw.replace(" ", "_").replace("/", "_"))
        slug = "_".join(part for part in slug.split("_") if part)
        if not slug:
            raise ValueError("Survey type slug is required")
        existing = db.execute(select(SurveyType).where(SurveyType.slug == slug)).scalar_one_or_none()
        if existing is not None:
            raise ValueError(f"A survey type with slug “{slug}” already exists")
        now = datetime.utcnow()
        row = SurveyType(
            id=str(uuid.uuid4()),
            slug=slug,
            name=name,
            description=str(payload.get("description") or "").strip() or None,
            is_active=bool(payload.get("is_active", True)),
            default_length=str(payload.get("default_length") or "standard").strip().lower()
            if str(payload.get("default_length") or "standard").strip().lower() in LENGTH_OPTIONS
            else "standard",
            min_length=max(1, min(10, int(payload.get("min_length") or 4))),
            max_length=max(4, min(12, int(payload.get("max_length") or 6))),
            supports_anonymous=bool(payload.get("supports_anonymous", True)),
            sort_order=int(payload.get("sort_order") or 100),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update_type(db: Session, row: SurveyType, payload: dict[str, Any]) -> SurveyType:
        if "name" in payload and str(payload.get("name") or "").strip():
            row.name = str(payload["name"]).strip()
        if "description" in payload:
            raw = payload.get("description")
            row.description = str(raw).strip() if raw is not None and str(raw).strip() else None
        if "is_active" in payload:
            row.is_active = bool(payload["is_active"])
        if "default_length" in payload:
            length = str(payload.get("default_length") or "standard").strip().lower()
            if length in LENGTH_OPTIONS:
                row.default_length = length
        if "min_length" in payload:
            row.min_length = max(1, min(10, int(payload["min_length"] or 4)))
        if "max_length" in payload:
            row.max_length = max(row.min_length, min(12, int(payload["max_length"] or 6)))
        if "supports_anonymous" in payload:
            row.supports_anonymous = bool(payload["supports_anonymous"])
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def question_count_for_length(length_key: str) -> int:
        return LENGTH_OPTIONS.get(str(length_key or "").strip().lower(), 5)
