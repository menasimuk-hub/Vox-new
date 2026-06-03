"""Survey type ↔ WhatsApp template mapping CRUD and default enforcement."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

VARIANT_STANDARD = "standard"
VARIANT_ANONYMOUS = "anonymous"


class SurveyTypeTemplateError(ValueError):
    pass


def mapping_to_dict(row: SurveyTypeTemplate, *, survey_type: SurveyType | None = None) -> dict[str, Any]:
    data = {
        "id": row.id,
        "survey_type_id": row.survey_type_id,
        "template_id": row.template_id,
        "usable_as_standard": bool(row.usable_as_standard),
        "usable_as_anonymous": bool(row.usable_as_anonymous),
        "is_default_standard": bool(row.is_default_standard),
        "is_default_anonymous": bool(row.is_default_anonymous),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if survey_type is not None:
        data["survey_type_name"] = survey_type.name
        data["survey_type_slug"] = survey_type.slug
    return data


class SurveyTypeTemplateService:
    @staticmethod
    def list_for_survey_type(db: Session, survey_type_id: str) -> list[SurveyTypeTemplate]:
        return list(
            db.execute(
                select(SurveyTypeTemplate)
                .where(SurveyTypeTemplate.survey_type_id == survey_type_id)
                .order_by(SurveyTypeTemplate.id.asc())
            ).scalars()
        )

    @staticmethod
    def list_for_template(db: Session, template_id: int) -> list[SurveyTypeTemplate]:
        return list(
            db.execute(
                select(SurveyTypeTemplate)
                .where(SurveyTypeTemplate.template_id == template_id)
                .order_by(SurveyTypeTemplate.id.asc())
            ).scalars()
        )

    @staticmethod
    def linked_survey_type_count(db: Session, template_id: int) -> int:
        return int(
            db.execute(
                select(func.count()).select_from(SurveyTypeTemplate).where(SurveyTypeTemplate.template_id == template_id)
            ).scalar_one()
            or 0
        )

    @staticmethod
    def template_counts_for_survey_type(db: Session, survey_type_id: str) -> dict[str, int]:
        rows = db.execute(
            select(SurveyTypeTemplate).where(SurveyTypeTemplate.survey_type_id == survey_type_id)
        ).scalars()
        standard = anonymous = 0
        for row in rows:
            if row.usable_as_standard:
                standard += 1
            if row.usable_as_anonymous:
                anonymous += 1
        return {"standard": standard, "anonymous": anonymous}

    @staticmethod
    def _clear_defaults(db: Session, survey_type_id: str, *, field: str) -> None:
        rows = SurveyTypeTemplateService.list_for_survey_type(db, survey_type_id)
        for row in rows:
            if field == "standard" and row.is_default_standard:
                row.is_default_standard = False
                row.updated_at = datetime.utcnow()
                db.add(row)
            if field == "anonymous" and row.is_default_anonymous:
                row.is_default_anonymous = False
                row.updated_at = datetime.utcnow()
                db.add(row)

    @staticmethod
    def upsert_mapping(
        db: Session,
        *,
        survey_type_id: str,
        template_id: int,
        usable_as_standard: bool = False,
        usable_as_anonymous: bool = False,
        is_default_standard: bool = False,
        is_default_anonymous: bool = False,
    ) -> SurveyTypeTemplate:
        if not usable_as_standard and not usable_as_anonymous and not is_default_standard and not is_default_anonymous:
            existing = db.execute(
                select(SurveyTypeTemplate).where(
                    SurveyTypeTemplate.survey_type_id == survey_type_id,
                    SurveyTypeTemplate.template_id == template_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                db.delete(existing)
                db.commit()
            raise SurveyTypeTemplateError("Mapping removed")

        if is_default_standard and not usable_as_standard:
            usable_as_standard = True
        if is_default_anonymous and not usable_as_anonymous:
            usable_as_anonymous = True

        row = db.execute(
            select(SurveyTypeTemplate).where(
                SurveyTypeTemplate.survey_type_id == survey_type_id,
                SurveyTypeTemplate.template_id == template_id,
            )
        ).scalar_one_or_none()
        now = datetime.utcnow()
        if row is None:
            row = SurveyTypeTemplate(
                survey_type_id=survey_type_id,
                template_id=template_id,
                created_at=now,
                updated_at=now,
            )
            db.add(row)

        row.usable_as_standard = bool(usable_as_standard)
        row.usable_as_anonymous = bool(usable_as_anonymous)
        row.is_default_standard = bool(is_default_standard)
        row.is_default_anonymous = bool(is_default_anonymous)
        row.updated_at = now

        if row.is_default_standard:
            SurveyTypeTemplateService._clear_defaults(db, survey_type_id, field="standard")
            row.is_default_standard = True
        if row.is_default_anonymous:
            SurveyTypeTemplateService._clear_defaults(db, survey_type_id, field="anonymous")
            row.is_default_anonymous = True

        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def replace_template_mappings(db: Session, template_id: int, mappings: list[dict[str, Any]]) -> list[SurveyTypeTemplate]:
        existing = SurveyTypeTemplateService.list_for_template(db, template_id)
        incoming_ids = {str(m.get("survey_type_id") or "").strip() for m in mappings if str(m.get("survey_type_id") or "").strip()}
        for row in existing:
            if row.survey_type_id not in incoming_ids:
                db.delete(row)
        db.flush()

        saved: list[SurveyTypeTemplate] = []
        defaults_std: dict[str, str | None] = {}
        defaults_anon: dict[str, str | None] = {}
        for item in mappings:
            stid = str(item.get("survey_type_id") or "").strip()
            if not stid:
                continue
            if item.get("is_default_standard"):
                defaults_std[stid] = stid
            if item.get("is_default_anonymous"):
                defaults_anon[stid] = stid

        for stid in defaults_std:
            SurveyTypeTemplateService._clear_defaults(db, stid, field="standard")
        for stid in defaults_anon:
            SurveyTypeTemplateService._clear_defaults(db, stid, field="anonymous")
        db.flush()

        for item in mappings:
            stid = str(item.get("survey_type_id") or "").strip()
            if not stid:
                continue
            usable_standard = bool(item.get("usable_as_standard"))
            usable_anonymous = bool(item.get("usable_as_anonymous"))
            is_default_standard = bool(item.get("is_default_standard"))
            is_default_anonymous = bool(item.get("is_default_anonymous"))
            if not any([usable_standard, usable_anonymous, is_default_standard, is_default_anonymous]):
                continue
            row = db.execute(
                select(SurveyTypeTemplate).where(
                    SurveyTypeTemplate.survey_type_id == stid,
                    SurveyTypeTemplate.template_id == template_id,
                )
            ).scalar_one_or_none()
            now = datetime.utcnow()
            if row is None:
                row = SurveyTypeTemplate(
                    survey_type_id=stid,
                    template_id=template_id,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
            row.usable_as_standard = usable_standard or is_default_standard
            row.usable_as_anonymous = usable_anonymous or is_default_anonymous
            row.is_default_standard = is_default_standard
            row.is_default_anonymous = is_default_anonymous
            row.updated_at = now
            saved.append(row)

        db.commit()
        for row in saved:
            db.refresh(row)
        return saved

    @staticmethod
    def resolve_default_template(
        db: Session,
        *,
        survey_type_id: str,
        variant: str,
        language: str | None = None,
    ) -> TelnyxWhatsappTemplate | None:
        variant_key = str(variant or VARIANT_STANDARD).strip().lower()
        mappings = SurveyTypeTemplateService.list_for_survey_type(db, survey_type_id)
        if not mappings:
            return None

        def pick(pool: list[SurveyTypeTemplate]) -> TelnyxWhatsappTemplate | None:
            templates: list[TelnyxWhatsappTemplate] = []
            for mapping in pool:
                tpl = db.get(TelnyxWhatsappTemplate, mapping.template_id)
                if tpl is None or not tpl.active_for_survey:
                    continue
                templates.append(tpl)
            if not templates:
                return None
            lang = str(language or "").strip()
            approved = [t for t in templates if str(t.status or "").upper() == "APPROVED"]
            search = approved or templates
            if lang:
                for tpl in search:
                    if str(tpl.language or "") == lang:
                        return tpl
            return search[0]

        if variant_key == VARIANT_ANONYMOUS:
            default = [m for m in mappings if m.is_default_anonymous and m.usable_as_anonymous]
            if default:
                return pick(default)
            usable = [m for m in mappings if m.usable_as_anonymous]
            return pick(usable)

        default = [m for m in mappings if m.is_default_standard and m.usable_as_standard]
        if default:
            return pick(default)
        usable = [m for m in mappings if m.usable_as_standard]
        return pick(usable)

    @staticmethod
    def mappings_payload_for_template(db: Session, template_id: int) -> list[dict[str, Any]]:
        rows = SurveyTypeTemplateService.list_for_template(db, template_id)
        payload: list[dict[str, Any]] = []
        for row in rows:
            st = db.get(SurveyType, row.survey_type_id)
            payload.append(mapping_to_dict(row, survey_type=st))
        return payload

    @staticmethod
    def all_survey_types_with_mapping_flags(db: Session, template_id: int) -> list[dict[str, Any]]:
        mappings = {
            row.survey_type_id: row
            for row in SurveyTypeTemplateService.list_for_template(db, template_id)
        }
        types = list(db.execute(select(SurveyType).order_by(SurveyType.sort_order.asc(), SurveyType.name.asc())).scalars())
        payload: list[dict[str, Any]] = []
        for st in types:
            mapping = mappings.get(st.id)
            payload.append(
                {
                    "survey_type_id": st.id,
                    "name": st.name,
                    "slug": st.slug,
                    "supports_anonymous": bool(st.supports_anonymous),
                    "linked": mapping is not None,
                    "usable_as_standard": bool(mapping.usable_as_standard) if mapping else False,
                    "usable_as_anonymous": bool(mapping.usable_as_anonymous) if mapping else False,
                    "is_default_standard": bool(mapping.is_default_standard) if mapping else False,
                    "is_default_anonymous": bool(mapping.is_default_anonymous) if mapping else False,
                }
            )
        return payload
