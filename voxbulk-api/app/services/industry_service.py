"""Industry CRUD and seed data for WA Survey."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.industry_deletion_tombstone import IndustryDeletionTombstone
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

DEFAULT_INDUSTRIES: list[dict[str, Any]] = [
    {"slug": "healthcare", "name": "Healthcare", "description": "Clinics, dental, hospitals, care providers.", "sort_order": 10},
    {"slug": "ecommerce", "name": "E-commerce", "description": "Online retail and delivery feedback.", "sort_order": 20},
    {"slug": "finance", "name": "Finance", "description": "Banking, insurance, and financial services.", "sort_order": 30},
    {"slug": "hospitality", "name": "Hospitality", "description": "Hotels, restaurants, venues.", "sort_order": 40},
    {"slug": "education", "name": "Education", "description": "Schools, training, and ed-tech.", "sort_order": 50},
    {"slug": "saas", "name": "SaaS / Technology", "description": "Software and digital product feedback.", "sort_order": 60},
    {"slug": "services", "name": "Services", "description": "Professional and consumer services feedback.", "sort_order": 35},
    {"slug": "general", "name": "General / Other", "description": "Cross-industry or unspecified vertical.", "sort_order": 90},
]

_SLUG_RE = re.compile(r"^[a-z0-9_]{2,64}$")

SYSTEM_SURVEY_INDUSTRY_SLUG = "system-survey-templates"


def _normalize_slug(raw: str) -> str:
    token = re.sub(r"[^a-z0-9_]+", "_", str(raw or "").strip().lower()).strip("_")
    return token


def industry_to_dict(row: Industry, *, survey_type_count: int | None = None) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "is_active": bool(row.is_active),
        "is_hidden": bool(getattr(row, "is_hidden", False)),
        "sort_order": int(row.sort_order or 100),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if survey_type_count is not None:
        payload["survey_type_count"] = int(survey_type_count)
    return payload


class IndustryService:
    @staticmethod
    def _tombstoned_slugs(db: Session) -> set[str]:
        rows = db.execute(select(IndustryDeletionTombstone.slug)).scalars().all()
        return {str(slug) for slug in rows if slug}

    @staticmethod
    def is_slug_tombstoned(db: Session, slug: str) -> bool:
        key = _normalize_slug(slug)
        if not key:
            return False
        return db.get(IndustryDeletionTombstone, key) is not None

    @staticmethod
    def record_deleted_slug(db: Session, *, slug: str, name: str | None = None) -> None:
        key = _normalize_slug(slug)
        if not key:
            return
        row = db.get(IndustryDeletionTombstone, key)
        if row is not None:
            return
        db.add(
            IndustryDeletionTombstone(
                slug=key,
                name=str(name or "").strip() or None,
                deleted_at=datetime.utcnow(),
            )
        )

    @staticmethod
    def ensure_defaults(db: Session) -> None:
        """Seed default industries only when the catalog is empty (first bootstrap).

        Never re-insert individual slugs that an admin deleted. Tombstoned slugs are
        skipped even on empty-catalog bootstrap.
        """
        existing_count = int(
            db.execute(select(func.count()).select_from(Industry)).scalar_one() or 0
        )
        if existing_count > 0:
            return
        tombstones = IndustryService._tombstoned_slugs(db)
        now = datetime.utcnow()
        changed = False
        for item in DEFAULT_INDUSTRIES:
            slug = str(item["slug"])
            if slug in tombstones:
                continue
            existing = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                Industry(
                    id=str(uuid.uuid4()),
                    slug=item["slug"],
                    name=item["name"],
                    description=item.get("description"),
                    is_active=True,
                    sort_order=int(item.get("sort_order") or 100),
                    created_at=now,
                    updated_at=now,
                )
            )
            changed = True
        if changed:
            db.commit()

    @staticmethod
    def list_industries(
        db: Session,
        *,
        active_only: bool = True,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        IndustryService.ensure_defaults(db)
        stmt = select(Industry).order_by(Industry.sort_order.asc(), Industry.name.asc())
        if active_only and not include_inactive:
            stmt = stmt.where(Industry.is_active.is_(True))
        stmt = stmt.where(or_(Industry.is_hidden.is_(False), Industry.is_hidden.is_(None)))
        rows = list(db.execute(stmt).scalars())
        return [industry_to_dict(r) for r in rows]

    @staticmethod
    def list_industries_admin(db: Session) -> list[dict[str, Any]]:
        IndustryService.ensure_defaults(db)
        rows = list(
            db.execute(select(Industry).order_by(Industry.sort_order.asc(), Industry.name.asc())).scalars()
        )
        counts: dict[str, int] = {}
        for industry_id, cnt in db.execute(
            select(SurveyType.industry_id, func.count())
            .group_by(SurveyType.industry_id)
        ):
            if industry_id:
                counts[str(industry_id)] = int(cnt or 0)
        return [industry_to_dict(r, survey_type_count=counts.get(r.id, 0)) for r in rows]

    @staticmethod
    def get_industry(db: Session, industry_id: str) -> Industry | None:
        tid = str(industry_id or "").strip()
        if not tid:
            return None
        return db.get(Industry, tid)

    @staticmethod
    def get_by_slug(db: Session, slug: str) -> Industry | None:
        key = _normalize_slug(slug)
        if not key:
            return None
        IndustryService.ensure_defaults(db)
        return db.execute(select(Industry).where(Industry.slug == key)).scalar_one_or_none()

    @staticmethod
    def require_industry_id(db: Session, industry_id: str) -> Industry:
        row = IndustryService.get_industry(db, industry_id)
        if row is None or not row.is_active:
            raise ValueError("A valid active industry is required")
        return row

    @staticmethod
    def default_industry(db: Session) -> Industry:
        IndustryService.ensure_defaults(db)
        row = IndustryService.get_by_slug(db, "general")
        if row is None:
            row = db.execute(select(Industry).order_by(Industry.sort_order.asc()).limit(1)).scalar_one()
        return row

    @staticmethod
    def survey_type_count(db: Session, industry_id: str) -> int:
        return int(
            db.execute(
                select(func.count()).select_from(SurveyType).where(SurveyType.industry_id == industry_id)
            ).scalar_one()
            or 0
        )

    @staticmethod
    def create_industry(db: Session, payload: dict[str, Any]) -> Industry:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("Industry name is required")
        slug = _normalize_slug(str(payload.get("slug") or name))
        if not slug or not _SLUG_RE.match(slug):
            raise ValueError("Industry slug must be 2–64 lowercase letters, numbers, or underscores")
        existing = db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none()
        if existing is not None:
            raise ValueError(f"An industry with slug “{slug}” already exists")
        now = datetime.utcnow()
        row = Industry(
            id=str(uuid.uuid4()),
            slug=slug,
            name=name,
            description=str(payload.get("description") or "").strip() or None,
            is_active=bool(payload.get("is_active", True)),
            sort_order=max(0, min(9999, int(payload.get("sort_order") or 100))),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update_industry(db: Session, row: Industry, payload: dict[str, Any]) -> Industry:
        if "name" in payload and str(payload.get("name") or "").strip():
            row.name = str(payload["name"]).strip()
        if "description" in payload:
            raw = payload.get("description")
            row.description = str(raw).strip() if raw is not None and str(raw).strip() else None
        if "slug" in payload and str(payload.get("slug") or "").strip():
            slug = _normalize_slug(str(payload["slug"]))
            if not slug or not _SLUG_RE.match(slug):
                raise ValueError("Industry slug must be 2–64 lowercase letters, numbers, or underscores")
            existing = db.execute(
                select(Industry).where(Industry.slug == slug, Industry.id != row.id)
            ).scalar_one_or_none()
            if existing is not None:
                raise ValueError(f"An industry with slug “{slug}” already exists")
            row.slug = slug
        if "sort_order" in payload:
            row.sort_order = max(0, min(9999, int(payload.get("sort_order") or row.sort_order or 100)))
        if "is_active" in payload:
            row.is_active = bool(payload["is_active"])
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def set_active(db: Session, row: Industry, *, is_active: bool) -> Industry:
        if bool(getattr(row, "is_hidden", False)) and not is_active:
            raise ValueError("The system survey-templates industry cannot be disabled.")
        row.is_active = bool(is_active)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_industry(db: Session, row: Industry) -> dict[str, Any]:
        """Delete an industry and its survey types, flows, packs, and templates."""
        from app.models.survey_flow import SurveyFlowDefinition
        from app.models.survey_session import SurveySession
        from app.models.survey_template_pack import SurveyTemplatePack
        from app.models.survey_type_template import SurveyTypeTemplate
        from app.services.survey_type_template_service import SurveyTypeTemplateService
        from app.services.telnyx_whatsapp_template_sync_service import (
            TelnyxWhatsappTemplateSyncError,
            TelnyxWhatsappTemplateSyncService,
        )

        if bool(getattr(row, "is_hidden", False)):
            raise ValueError("The system survey-templates industry cannot be deleted.")

        industry_id = row.id
        industry_slug = str(row.slug or "")
        industry_name = str(row.name or "")
        survey_types = list(
            db.execute(select(SurveyType).where(SurveyType.industry_id == industry_id)).scalars()
        )
        survey_type_ids = [st.id for st in survey_types]
        warnings: list[str] = []

        flows: list[SurveyFlowDefinition] = []
        if survey_type_ids:
            flows = list(
                db.execute(
                    select(SurveyFlowDefinition).where(
                        SurveyFlowDefinition.survey_type_id.in_(survey_type_ids)
                    )
                ).scalars()
            )
            flow_ids = [flow.id for flow in flows]
            if flow_ids:
                db.execute(
                    update(SurveySession)
                    .where(SurveySession.flow_definition_id.in_(flow_ids))
                    .values(flow_definition_id=None)
                )
            db.execute(
                update(SurveySession)
                .where(SurveySession.survey_type_id.in_(survey_type_ids))
                .values(survey_type_id=None)
            )
            db.flush()

        for flow in flows:
            db.delete(flow)

        for pack in db.execute(
            select(SurveyTemplatePack).where(SurveyTemplatePack.industry_id == industry_id)
        ).scalars():
            db.delete(pack)
        db.execute(delete(SurveyTypeTemplate).where(SurveyTypeTemplate.industry_id == industry_id))
        db.flush()

        template_ids: set[int] = set()
        for st in survey_types:
            for mapping in SurveyTypeTemplateService.list_for_survey_type(db, st.id):
                template_ids.add(int(mapping.template_id))
        for tpl in db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.industry_id == industry_id)
        ).scalars():
            template_ids.add(int(tpl.id))

        deleted_templates = 0
        for tid in sorted(template_ids):
            tpl = db.get(TelnyxWhatsappTemplate, tid)
            if tpl is None:
                continue
            record_id = str(tpl.telnyx_record_id or "").strip()
            if record_id and not record_id.startswith("local-"):
                try:
                    TelnyxWhatsappTemplateSyncService.delete_remote_template(db, record_id)
                except TelnyxWhatsappTemplateSyncError as exc:
                    warnings.append(f"{tpl.name}: Telnyx delete failed; removed locally ({exc})")
            for mapping in SurveyTypeTemplateService.list_for_template(db, int(tpl.id)):
                db.delete(mapping)
            db.delete(tpl)
            deleted_templates += 1
        db.flush()

        if survey_type_ids:
            db.execute(
                update(TelnyxWhatsappTemplate)
                .where(TelnyxWhatsappTemplate.survey_type_id.in_(survey_type_ids))
                .values(survey_type_id=None)
            )

        deleted_types = 0
        for st in survey_types:
            fresh = db.get(SurveyType, st.id)
            if fresh is not None:
                db.delete(fresh)
                deleted_types += 1

        IndustryService.record_deleted_slug(db, slug=industry_slug, name=industry_name)
        db.delete(row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError(
                "Could not delete industry — linked survey data still references it. "
                "Remove or archive related survey orders first."
            ) from exc

        result: dict[str, Any] = {
            "ok": True,
            "deleted_industry_id": industry_id,
            "deleted_industry_slug": industry_slug,
            "deleted_survey_types": deleted_types,
            "deleted_templates": deleted_templates,
        }
        if warnings:
            result["warnings"] = warnings
        return result
