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
from app.models.industry_organisation import IndustryOrganisation
from app.models.industry_deletion_tombstone import IndustryDeletionTombstone
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
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


def industry_to_dict(
    row: Industry,
    *,
    survey_type_count: int | None = None,
    template_count: int | None = None,
    approved_template_count: int | None = None,
    pending_template_count: int | None = None,
    rejected_template_count: int | None = None,
    org_ids: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "is_active": bool(row.is_active),
        "is_hidden": bool(getattr(row, "is_hidden", False)),
        "visibility_mode": str(getattr(row, "visibility_mode", None) or "all"),
        "source_industry_id": getattr(row, "source_industry_id", None),
        "sort_order": int(row.sort_order or 100),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if survey_type_count is not None:
        payload["survey_type_count"] = int(survey_type_count)
    if template_count is not None:
        payload["template_count"] = int(template_count)
    if approved_template_count is not None:
        payload["approved_template_count"] = int(approved_template_count)
    if pending_template_count is not None:
        payload["pending_template_count"] = int(pending_template_count)
    if rejected_template_count is not None:
        payload["rejected_template_count"] = int(rejected_template_count)
    # green = all approved, red = any rejected, orange = pending/none rejected
    total = int(payload.get("template_count") or 0)
    approved = int(payload.get("approved_template_count") or 0)
    rejected = int(payload.get("rejected_template_count") or 0)
    if total <= 0:
        payload["approval_health"] = "empty"
    elif rejected > 0:
        payload["approval_health"] = "rejected"
    elif approved >= total:
        payload["approval_health"] = "approved"
    else:
        payload["approval_health"] = "pending"
    if org_ids is not None:
        payload["org_ids"] = org_ids
    return payload


def _is_template_approved(row: TelnyxWhatsappTemplate) -> bool:
    return str(row.status or "").strip().upper() == "APPROVED"


def _template_ids_for_industry(db: Session, industry_id: str) -> set[int]:
    from app.services.survey_type_template_service import template_name_survey_slug

    ids: set[int] = set()
    for tid in db.execute(
        select(TelnyxWhatsappTemplate.id).where(TelnyxWhatsappTemplate.industry_id == industry_id)
    ).scalars():
        ids.add(int(tid))
    for tid in db.execute(
        select(SurveyTypeTemplate.template_id).where(SurveyTypeTemplate.industry_id == industry_id)
    ).scalars():
        ids.add(int(tid))
    survey_types = list(
        db.execute(select(SurveyType).where(SurveyType.industry_id == industry_id)).scalars()
    )
    survey_type_ids = [st.id for st in survey_types]
    if survey_type_ids:
        for tid in db.execute(
            select(TelnyxWhatsappTemplate.id).where(
                TelnyxWhatsappTemplate.survey_type_id.in_(survey_type_ids)
            )
        ).scalars():
            ids.add(int(tid))
    # Orphans (industry_id/survey_type_id null) whose Meta name matches a type slug in this industry.
    known_slugs = [str(st.slug or "").strip().lower() for st in survey_types if str(st.slug or "").strip()]
    if known_slugs:
        slug_set = set(known_slugs)
        orphans = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.name.ilike("voxbulk_survey_%"),
                    TelnyxWhatsappTemplate.industry_id.is_(None),
                )
            ).scalars()
        )
        for row in orphans:
            name_slug = template_name_survey_slug(str(row.name or ""), known_slugs=known_slugs)
            if name_slug and name_slug in slug_set:
                ids.add(int(row.id))
    return ids


def _template_count_payload(db: Session, template_ids: set[int]) -> dict[str, int]:
    """Count one primary per survey-type group (same rules as industry list)."""
    if not template_ids:
        return {
            "template_count": 0,
            "approved_template_count": 0,
            "pending_template_count": 0,
            "rejected_template_count": 0,
        }
    from app.services.survey_type_template_service import template_name_survey_slug

    rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.id.in_(template_ids))
        ).scalars()
    )
    # Group by survey_type_id or name slug so card totals match the hub list.
    type_ids = {str(r.survey_type_id or "") for r in rows if r.survey_type_id}
    type_rows = []
    if type_ids:
        type_rows = list(db.execute(select(SurveyType).where(SurveyType.id.in_(list(type_ids)))).scalars())
    known_slugs = [str(st.slug or "") for st in type_rows]
    slug_to_key = {str(st.slug or "").strip().lower(): str(st.id) for st in type_rows if st.slug}
    groups: dict[str, list] = {}
    for row in rows:
        key = str(row.survey_type_id or "").strip()
        if not key:
            name_slug = template_name_survey_slug(str(row.name or ""), known_slugs=known_slugs)
            key = slug_to_key.get(str(name_slug or "")) or f"row:{row.id}"
        groups.setdefault(key, []).append(row)

    total = len(groups)
    approved = 0
    rejected = 0
    pending = 0
    for group in groups.values():
        statuses = {str(r.status or "").strip().upper() for r in group}
        if "REJECTED" in statuses:
            rejected += 1
        elif any(s in statuses for s in ("PENDING", "SUBMITTED", "IN_APPEAL")):
            pending += 1
        elif all(_is_template_approved(r) for r in group):
            approved += 1
        else:
            pending += 1
    return {
        "template_count": total,
        "approved_template_count": approved,
        "pending_template_count": pending,
        "rejected_template_count": rejected,
    }


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
    def list_industries_admin(
        db: Session,
        *,
        include_hidden: bool = True,
        include_inactive: bool = True,
    ) -> list[dict[str, Any]]:
        """Full industries table for the Industries admin page."""
        IndustryService.ensure_defaults(db)
        stmt = select(Industry).order_by(Industry.sort_order.asc(), Industry.name.asc())
        if not include_inactive:
            stmt = stmt.where(Industry.is_active.is_(True))
        if not include_hidden:
            stmt = stmt.where(or_(Industry.is_hidden.is_(False), Industry.is_hidden.is_(None)))
        rows = list(db.execute(stmt).scalars())
        counts: dict[str, int] = {}
        for industry_id, cnt in db.execute(
            select(SurveyType.industry_id, func.count())
            .group_by(SurveyType.industry_id)
        ):
            if industry_id:
                counts[str(industry_id)] = int(cnt or 0)
        return [industry_to_dict(r, survey_type_count=counts.get(r.id, 0)) for r in rows]

    @staticmethod
    def wa_survey_overview(db: Session) -> dict[str, Any]:
        """KPI totals and per-industry template counts for the WA Survey admin landing page."""
        IndustryService.ensure_defaults(db)
        rows = list(
            db.execute(select(Industry).order_by(Industry.sort_order.asc(), Industry.name.asc())).scalars()
        )
        type_counts: dict[str, int] = {}
        for industry_id, cnt in db.execute(
            select(SurveyType.industry_id, func.count()).group_by(SurveyType.industry_id)
        ):
            if industry_id:
                type_counts[str(industry_id)] = int(cnt or 0)

        industries: list[dict[str, Any]] = []
        for row in rows:
            template_ids = _template_ids_for_industry(db, row.id)
            counts = _template_count_payload(db, template_ids)
            industries.append(
                industry_to_dict(
                    row,
                    survey_type_count=type_counts.get(row.id, 0),
                    template_count=counts["template_count"],
                    approved_template_count=counts["approved_template_count"],
                    pending_template_count=counts["pending_template_count"],
                    rejected_template_count=counts["rejected_template_count"],
                )
            )

        all_templates = list(db.execute(select(TelnyxWhatsappTemplate)).scalars())
        total_templates = len(all_templates)
        approved_templates = sum(1 for tpl in all_templates if _is_template_approved(tpl))
        visible_industries = [row for row in rows if not bool(getattr(row, "is_hidden", False))]

        return {
            "ok": True,
            "kpis": {
                "total_industries": len(visible_industries),
                "total_templates": total_templates,
                "approved_templates": approved_templates,
                "pending_templates": max(0, total_templates - approved_templates),
            },
            "industries": industries,
        }

    @staticmethod
    def list_industries_selectable(db: Session) -> list[dict[str, Any]]:
        """Active, non-hidden industries for filters and customer-facing pickers."""
        return IndustryService.list_industries(db, active_only=True, include_inactive=False)

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
        visibility_mode = str(payload.get("visibility_mode") or "all").strip().lower()
        if visibility_mode not in {"all", "restricted"}:
            org_ids_raw = payload.get("org_ids")
            visibility_mode = "restricted" if org_ids_raw else "all"
        row = Industry(
            id=str(uuid.uuid4()),
            slug=slug,
            name=name,
            description=str(payload.get("description") or "").strip() or None,
            is_active=bool(payload.get("is_active", True)),
            sort_order=max(0, min(9999, int(payload.get("sort_order") or 100))),
            visibility_mode=visibility_mode,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        if visibility_mode == "restricted" or payload.get("org_ids"):
            IndustryService.set_industry_orgs(db, row.id, list(payload.get("org_ids") or []))
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
        if "visibility_mode" in payload:
            mode = str(payload.get("visibility_mode") or "all").strip().lower()
            if mode in {"all", "restricted"}:
                row.visibility_mode = mode
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        if "org_ids" in payload:
            IndustryService.set_industry_orgs(db, row.id, list(payload.get("org_ids") or []))
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

        from app.services.survey_type_template_service import template_name_survey_slug

        template_ids: set[int] = set()
        for st in survey_types:
            for mapping in SurveyTypeTemplateService.list_for_survey_type(db, st.id):
                template_ids.add(int(mapping.template_id))
        for tpl in db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.industry_id == industry_id)
        ).scalars():
            template_ids.add(int(tpl.id))
        # Orphans named for this industry's survey type slugs.
        known_slugs = [str(st.slug or "").strip().lower() for st in survey_types if str(st.slug or "").strip()]
        slug_set = set(known_slugs)
        if known_slugs:
            for tpl in db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.name.ilike("voxbulk_survey_%"),
                    TelnyxWhatsappTemplate.industry_id.is_(None),
                )
            ).scalars():
                name_slug = template_name_survey_slug(str(tpl.name or ""), known_slugs=known_slugs)
                if name_slug and name_slug in slug_set:
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

    @staticmethod
    def industry_org_ids(db: Session, industry_id: str) -> list[str]:
        return list(
            db.execute(
                select(IndustryOrganisation.org_id)
                .where(IndustryOrganisation.industry_id == industry_id)
                .order_by(IndustryOrganisation.created_at.asc())
            ).scalars()
        )

    @staticmethod
    def set_industry_orgs(db: Session, industry_id: str, org_ids: list[str]) -> list[str]:
        cleaned = []
        seen: set[str] = set()
        for raw in org_ids or []:
            oid = str(raw or "").strip()
            if not oid or oid in seen:
                continue
            seen.add(oid)
            cleaned.append(oid)
        db.execute(delete(IndustryOrganisation).where(IndustryOrganisation.industry_id == industry_id))
        now = datetime.utcnow()
        for oid in cleaned:
            db.add(IndustryOrganisation(id=str(uuid.uuid4()), industry_id=industry_id, org_id=oid, created_at=now))
        db.commit()
        return cleaned

    @staticmethod
    def _industry_visible_to_org(db: Session, row: Industry, org_id: str | None) -> bool:
        if not row.is_active or bool(getattr(row, "is_hidden", False)):
            return False
        mode = str(getattr(row, "visibility_mode", None) or "all").strip().lower()
        if mode != "restricted":
            return True
        if not org_id:
            return False
        linked = db.execute(
            select(IndustryOrganisation.id).where(
                IndustryOrganisation.industry_id == row.id,
                IndustryOrganisation.org_id == org_id,
            )
        ).scalar_one_or_none()
        return linked is not None

    @staticmethod
    def list_industries_for_org(db: Session, org_id: str) -> list[dict[str, Any]]:
        rows = IndustryService.list_industries(db, active_only=True, include_inactive=False)
        visible: list[dict[str, Any]] = []
        for payload in rows:
            row = IndustryService.get_industry(db, str(payload.get("id") or ""))
            if row is None:
                continue
            if IndustryService._industry_visible_to_org(db, row, org_id):
                visible.append(payload)
        return visible

    @staticmethod
    def duplicate_industry(db: Session, source: Industry, payload: dict[str, Any]) -> Industry:
        if bool(getattr(source, "is_hidden", False)):
            raise ValueError("System industries cannot be duplicated")
        name = str(payload.get("name") or f"{source.name} (copy)").strip()
        slug_base = _normalize_slug(str(payload.get("slug") or f"{source.slug}_copy"))
        slug = slug_base
        suffix = 1
        while db.execute(select(Industry).where(Industry.slug == slug)).scalar_one_or_none() is not None:
            suffix += 1
            slug = f"{slug_base}_{suffix}"
        org_ids = [str(x).strip() for x in (payload.get("org_ids") or []) if str(x).strip()]
        visibility_mode = str(payload.get("visibility_mode") or ("restricted" if org_ids else "all")).strip().lower()
        if visibility_mode not in {"all", "restricted"}:
            visibility_mode = "restricted" if org_ids else "all"
        now = datetime.utcnow()
        copy = Industry(
            id=str(uuid.uuid4()),
            slug=slug,
            name=name,
            description=source.description,
            is_active=False,
            is_hidden=False,
            visibility_mode=visibility_mode,
            source_industry_id=source.id,
            sort_order=int(source.sort_order or 100),
            created_at=now,
            updated_at=now,
        )
        db.add(copy)
        db.flush()

        type_map: dict[str, str] = {}
        source_types = list(db.execute(select(SurveyType).where(SurveyType.industry_id == source.id)).scalars())
        for st in source_types:
            new_type = SurveyType(
                id=str(uuid.uuid4()),
                industry_id=copy.id,
                slug=st.slug,
                name=st.name,
                description=st.description,
                is_active=bool(st.is_active),
                default_length=st.default_length,
                min_length=int(st.min_length or 4),
                max_length=int(st.max_length or 6),
                supports_anonymous=bool(st.supports_anonymous),
                system_template_kind=st.system_template_kind,
                sort_order=int(st.sort_order or 100),
                created_at=now,
                updated_at=now,
            )
            db.add(new_type)
            db.flush()
            type_map[st.id] = new_type.id

        template_map: dict[int, int] = {}
        tpl_stmt = select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.industry_id == source.id)
        if type_map:
            tpl_stmt = select(TelnyxWhatsappTemplate).where(
                or_(
                    TelnyxWhatsappTemplate.industry_id == source.id,
                    TelnyxWhatsappTemplate.survey_type_id.in_(list(type_map.keys())),
                )
            )
        source_templates = list(db.execute(tpl_stmt).scalars())
        for tpl in source_templates:
            new_type_id = type_map.get(str(tpl.survey_type_id or "")) if tpl.survey_type_id else None
            local_id = f"local-copy-{uuid.uuid4()}"
            clone = TelnyxWhatsappTemplate(
                telnyx_record_id=local_id,
                template_id=local_id,
                name=tpl.name,
                language=tpl.language,
                category=tpl.category,
                status="DRAFT",
                sales_template_key=tpl.sales_template_key,
                body_preview=tpl.body_preview,
                components_json=tpl.components_json,
                waba_id=tpl.waba_id,
                rejection_reason=None,
                industry_id=copy.id,
                survey_type_id=new_type_id,
                variant_type=tpl.variant_type,
                step_role=tpl.step_role,
                outcome_key=tpl.outcome_key,
                outcome_variables_json=tpl.outcome_variables_json,
                privacy_mode=tpl.privacy_mode,
                pack_id=None,
                parent_template_id=None,
                display_name=tpl.display_name,
                customer_description=tpl.customer_description,
                draft_components_json=tpl.draft_components_json or tpl.components_json,
                example_values_json=tpl.example_values_json,
                local_sync_status="draft",
                active_for_survey=bool(tpl.active_for_survey),
                active_for_interview=bool(tpl.active_for_interview),
                synced_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(clone)
            db.flush()
            template_map[int(tpl.id)] = int(clone.id)

        for mapping in db.execute(
            select(SurveyTypeTemplate).where(SurveyTypeTemplate.industry_id == source.id)
        ).scalars():
            new_type_id = type_map.get(mapping.survey_type_id)
            new_template_id = template_map.get(int(mapping.template_id))
            if not new_type_id or not new_template_id:
                continue
            db.add(
                SurveyTypeTemplate(
                    industry_id=copy.id,
                    survey_type_id=new_type_id,
                    template_id=new_template_id,
                    usable_as_standard=bool(mapping.usable_as_standard),
                    usable_as_anonymous=bool(mapping.usable_as_anonymous),
                    is_default_standard=bool(mapping.is_default_standard),
                    is_default_anonymous=bool(mapping.is_default_anonymous),
                    privacy_mode=mapping.privacy_mode,
                    created_at=now,
                    updated_at=now,
                )
            )

        if org_ids:
            IndustryService.set_industry_orgs(db, copy.id, org_ids)
        else:
            db.commit()
        db.refresh(copy)
        return copy
