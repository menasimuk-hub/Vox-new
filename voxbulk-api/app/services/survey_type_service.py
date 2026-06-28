"""Survey Type CRUD and default seed data for WA Survey admin."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService, industry_to_dict
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


def survey_type_to_dict(
    row: SurveyType,
    *,
    template_counts: dict[str, int] | None = None,
    industry: Industry | None = None,
) -> dict[str, Any]:
    counts = template_counts or {}
    payload = {
        "id": row.id,
        "industry_id": row.industry_id,
        "slug": row.slug,
        "name": row.name,
        "description": row.description,
        "is_active": bool(row.is_active),
        "default_length": row.default_length,
        "min_length": int(row.min_length or 4),
        "max_length": int(row.max_length or 6),
        "supports_anonymous": bool(row.supports_anonymous),
        "system_template_kind": row.system_template_kind,
        "sort_order": int(row.sort_order or 100),
        "standard_template_count": int(counts.get("standard") or 0),
        "anonymous_template_count": int(counts.get("anonymous") or 0),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if industry is not None:
        payload["industry_slug"] = industry.slug
        payload["industry_name"] = industry.name
    return payload


class SurveyTypeService:
    @staticmethod
    def ensure_defaults(db: Session) -> None:
        IndustryService.ensure_defaults(db)
        default_industry = IndustryService.default_industry(db)
        now = datetime.utcnow()
        for item in DEFAULT_SURVEY_TYPES:
            existing = db.execute(
                select(SurveyType).where(
                    SurveyType.industry_id == default_industry.id,
                    SurveyType.slug == item["slug"],
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                SurveyType(
                    id=str(uuid.uuid4()),
                    industry_id=default_industry.id,
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
    def list_types(db: Session, *, industry_id: str | None = None, exclude_disabled: bool = False) -> list[dict[str, Any]]:
        SurveyTypeService.ensure_defaults(db)
        stmt = select(SurveyType).order_by(SurveyType.sort_order.asc(), SurveyType.name.asc())
        if industry_id:
            stmt = stmt.where(SurveyType.industry_id == str(industry_id).strip())
        else:
            stmt = stmt.where(SurveyType.system_template_kind.is_(None))
        rows = list(db.execute(stmt).scalars())
        if exclude_disabled:
            from app.services.disabled_wa_template_service import DisabledWaTemplateService

            hidden = DisabledWaTemplateService.hidden_platform_survey_type_ids(db)
            if hidden:
                rows = [r for r in rows if r.id not in hidden]
        industry_cache: dict[str, Industry] = {}
        payload: list[dict[str, Any]] = []
        for row in rows:
            industry = industry_cache.get(row.industry_id)
            if industry is None and row.industry_id:
                industry = db.get(Industry, row.industry_id)
                if industry is not None:
                    industry_cache[row.industry_id] = industry
            counts = SurveyTypeService._template_counts(db, row.id)
            data = survey_type_to_dict(row, template_counts=counts, industry=industry)
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
            wa_count = int(counts.get("standard") or 0) + int(counts.get("anonymous") or 0)
            data["has_wa_template"] = wa_count > 0
            payload.append(data)
        return payload

    @staticmethod
    def get_type(db: Session, type_id: str) -> SurveyType | None:
        tid = str(type_id or "").strip()
        if not tid:
            return None
        return db.get(SurveyType, tid)

    @staticmethod
    def get_by_slug(
        db: Session,
        slug: str,
        *,
        industry_id: str | None = None,
        default_industry_fallback: bool = True,
    ) -> SurveyType | None:
        """Resolve survey type by slug. Without industry_id, returns a row only when unambiguous."""
        key = str(slug or "").strip().lower()
        if not key:
            return None
        if industry_id:
            return db.execute(
                select(SurveyType).where(
                    SurveyType.slug == key,
                    SurveyType.industry_id == str(industry_id).strip(),
                )
            ).scalar_one_or_none()

        rows = list(db.execute(select(SurveyType).where(SurveyType.slug == key)).scalars())
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1 and default_industry_fallback:
            default = IndustryService.default_industry(db)
            scoped = [r for r in rows if r.industry_id == default.id]
            if len(scoped) == 1:
                return scoped[0]
        return None

    @staticmethod
    def resolve_unique_by_slug(
        db: Session,
        slug: str,
        *,
        survey_type_id: str | None = None,
    ) -> SurveyType | None:
        """Telnyx/sync helper — never guess when the same slug exists in multiple industries."""
        key = str(slug or "").strip().lower()
        if not key:
            return None
        scoped_id = str(survey_type_id or "").strip()
        if scoped_id:
            row = db.get(SurveyType, scoped_id)
            if row is not None and str(row.slug or "").strip().lower() == key:
                return row
            return None
        rows = list(db.execute(select(SurveyType).where(SurveyType.slug == key)).scalars())
        if len(rows) == 1:
            return rows[0]
        return None

    @staticmethod
    def survey_types_matching_name_slug(db: Session, name: str, *, known_slugs: list[str] | None = None) -> list[SurveyType]:
        from app.services.survey_type_template_service import template_name_matches_survey_slug, template_name_survey_slug

        all_types = list(db.execute(select(SurveyType)).scalars())
        slugs = known_slugs or [str(st.slug or "") for st in all_types]
        name_slug = template_name_survey_slug(name, known_slugs=slugs)
        if name_slug:
            return [st for st in all_types if str(st.slug or "").strip().lower() == name_slug]
        return [st for st in all_types if template_name_matches_survey_slug(name, st.slug)]

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
        industry = IndustryService.require_industry_id(db, str(payload.get("industry_id") or ""))
        existing = db.execute(
            select(SurveyType).where(SurveyType.industry_id == industry.id, SurveyType.slug == slug)
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError(f"A survey type with slug “{slug}” already exists in this industry")
        now = datetime.utcnow()
        row = SurveyType(
            id=str(uuid.uuid4()),
            industry_id=industry.id,
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
        if "industry_id" in payload and str(payload.get("industry_id") or "").strip():
            industry = IndustryService.require_industry_id(db, str(payload["industry_id"]))
            row.industry_id = industry.id
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def question_count_for_length(length_key: str) -> int:
        return LENGTH_OPTIONS.get(str(length_key or "").strip().lower(), 5)

    @staticmethod
    def delete_type(db: Session, row: SurveyType) -> dict[str, Any]:
        """Delete a survey type, its flows, packs, templates (Telnyx + DB), and mappings."""
        from app.models.survey_flow import SurveyFlowDefinition
        from app.models.survey_session import SurveySession
        from app.models.survey_template_pack import SurveyTemplatePack
        from app.services.telnyx_whatsapp_template_sync_service import (
            TelnyxWhatsappTemplateSyncError,
            TelnyxWhatsappTemplateSyncService,
        )

        if str(row.system_template_kind or "").strip():
            raise ValueError("System survey template types cannot be deleted.")

        type_id = str(row.id)
        type_name = str(row.name or "")
        warnings: list[str] = []

        flows = list(
            db.execute(
                select(SurveyFlowDefinition).where(SurveyFlowDefinition.survey_type_id == type_id)
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
            update(SurveySession).where(SurveySession.survey_type_id == type_id).values(survey_type_id=None)
        )
        db.flush()

        for flow in flows:
            db.delete(flow)

        for pack in db.execute(
            select(SurveyTemplatePack).where(SurveyTemplatePack.survey_type_id == type_id)
        ).scalars():
            db.delete(pack)

        template_ids: set[int] = set()
        for mapping in SurveyTypeTemplateService.list_for_survey_type(db, type_id):
            template_ids.add(int(mapping.template_id))
        for tpl in db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.survey_type_id == type_id)
        ).scalars():
            template_ids.add(int(tpl.id))

        db.execute(delete(SurveyTypeTemplate).where(SurveyTypeTemplate.survey_type_id == type_id))
        db.flush()

        deleted_templates = 0
        telnyx_deleted = 0
        for tid in sorted(template_ids):
            tpl = db.get(TelnyxWhatsappTemplate, tid)
            if tpl is None:
                continue
            record_id = str(tpl.telnyx_record_id or "").strip()
            if record_id and not record_id.startswith("local-"):
                try:
                    TelnyxWhatsappTemplateSyncService.delete_remote_template(db, record_id)
                    telnyx_deleted += 1
                except TelnyxWhatsappTemplateSyncError as exc:
                    warnings.append(f"{tpl.name}: Telnyx delete failed; removed locally ({exc})")
            for mapping in SurveyTypeTemplateService.list_for_template(db, int(tpl.id)):
                db.delete(mapping)
            db.delete(tpl)
            deleted_templates += 1
        db.flush()

        db.execute(
            update(TelnyxWhatsappTemplate)
            .where(TelnyxWhatsappTemplate.survey_type_id == type_id)
            .values(survey_type_id=None)
        )

        db.delete(row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError(
                "Could not delete survey type — linked survey data still references it. "
                "Remove or archive related survey orders first."
            ) from exc

        result: dict[str, Any] = {
            "ok": True,
            "deleted_survey_type_id": type_id,
            "deleted_survey_type_name": type_name,
            "deleted_templates": deleted_templates,
            "telnyx_deleted": telnyx_deleted,
        }
        if warnings:
            result["warnings"] = warnings
        return result

    @staticmethod
    def delete_types_bulk(db: Session, type_ids: list[str]) -> dict[str, Any]:
        ids = [str(tid or "").strip() for tid in type_ids if str(tid or "").strip()]
        if not ids:
            raise ValueError("Select at least one survey type to delete.")

        deleted: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []

        for type_id in ids:
            row = SurveyTypeService.get_type(db, type_id)
            if row is None:
                errors.append(f"{type_id}: not found")
                continue
            try:
                result = SurveyTypeService.delete_type(db, row)
                deleted.append(
                    {
                        "survey_type_id": type_id,
                        "deleted_templates": result.get("deleted_templates", 0),
                        "telnyx_deleted": result.get("telnyx_deleted", 0),
                    }
                )
                for warning in result.get("warnings") or []:
                    warnings.append(f"{row.name}: {warning}")
            except ValueError as exc:
                errors.append(f"{row.name}: {exc}")

        if not deleted and errors:
            raise ValueError(errors[0] if len(errors) == 1 else "; ".join(errors))

        payload: dict[str, Any] = {
            "ok": True,
            "deleted_count": len(deleted),
            "deleted": deleted,
        }
        if warnings:
            payload["warnings"] = warnings
        if errors:
            payload["errors"] = errors
        return payload
