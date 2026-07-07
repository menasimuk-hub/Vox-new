"""Survey type ↔ WhatsApp template mapping CRUD and default enforcement."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate

from app.services.survey_industry_scope import (
    SurveyIndustryScopeError,
    apply_industry_to_template,
    assert_industry_match,
    resolve_survey_type_industry_id,
    template_matches_survey_industry,
)
from app.services.wa_template_privacy import (
    PRIVACY_MODE_OFF,
    PRIVACY_MODE_ON,
    normalize_privacy_mode,
    resolve_mapping_privacy_mode,
    resolve_row_privacy_mode,
)

_PACK_PREFIX_RE = re.compile(r"^voxbulk_survey_", re.I)
_LEGACY_VARIANT_RE = re.compile(r"^voxbulk_survey_([a-z0-9_]+)_(standard|anonymous)$", re.I)


class SurveyTypeTemplateError(ValueError):
    pass


def template_name_matches_survey_slug(name: str | None, survey_slug: str | None) -> bool:
    slug = str(survey_slug or "").strip().lower()
    if not slug:
        return False
    lower = str(name or "").strip().lower()
    if lower.startswith(f"voxbulk_survey_{slug}_"):
        return True
    return bool(re.match(rf"^voxbulk_survey_{re.escape(slug)}_(standard|anonymous)$", lower))


def template_name_survey_slug(name: str | None, *, known_slugs: list[str] | None = None) -> str | None:
    """Extract survey slug from voxbulk_survey_{slug}_* names (longest known slug wins)."""
    lower = str(name or "").strip().lower()
    if not lower.startswith("voxbulk_survey_"):
        return None
    rest = lower[len("voxbulk_survey_") :]
    legacy = re.match(r"^([a-z0-9_]+)_(standard|anonymous)$", rest)
    if legacy:
        return legacy.group(1)
    if known_slugs:
        for slug in sorted({str(s or "").strip().lower() for s in known_slugs if str(s or "").strip()}, key=len, reverse=True):
            if rest.startswith(f"{slug}_"):
                return slug
    return None


def template_belongs_to_survey_type(row: TelnyxWhatsappTemplate, survey_type: SurveyType) -> bool:
    """True when a template is owned by / named for this survey type (not a mistaken sync link)."""
    if str(row.survey_type_id or "").strip() == str(survey_type.id):
        return True
    return template_name_matches_survey_slug(row.name, survey_type.slug)


def mapping_to_dict(row: SurveyTypeTemplate, *, survey_type: SurveyType | None = None) -> dict[str, Any]:
    data = {
        "id": row.id,
        "survey_type_id": row.survey_type_id,
        "template_id": row.template_id,
        "usable_as_standard": bool(row.usable_as_standard),
        "usable_as_anonymous": bool(row.usable_as_anonymous),
        "is_default_standard": bool(row.is_default_standard),
        "is_default_anonymous": bool(row.is_default_anonymous),
        "privacy_mode": resolve_mapping_privacy_mode(row),
        "industry_id": row.industry_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if survey_type is not None:
        data["survey_type_name"] = survey_type.name
        data["survey_type_slug"] = survey_type.slug
        data["industry_id"] = survey_type.industry_id
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
        from app.services.survey_whatsapp_template_service import (
            template_row_is_sendable_on_meta,
            template_row_must_send_as_session_text,
        )

        survey_type = db.get(SurveyType, survey_type_id)
        rows = SurveyTypeTemplateService.list_for_survey_type(db, survey_type_id)
        standard = anonymous = 0
        for row in rows:
            tpl = db.get(TelnyxWhatsappTemplate, row.template_id)
            if tpl is None or not tpl.active_for_survey:
                continue
            if not template_row_is_sendable_on_meta(tpl) and not template_row_must_send_as_session_text(tpl):
                continue
            if survey_type is not None:
                if not template_belongs_to_survey_type(tpl, survey_type):
                    continue
                if not template_matches_survey_industry(tpl, survey_type, mapping=row):
                    continue
            if row.usable_as_standard:
                standard += 1
            if row.usable_as_anonymous:
                anonymous += 1
        return {"standard": standard, "anonymous": anonymous}

    @staticmethod
    def unlink_template_from_survey_type(
        db: Session,
        *,
        survey_type_id: str,
        template_id: int,
    ) -> dict[str, Any]:
        """Remove a template from this survey type's step bank (survey-scoped delete)."""
        survey_type = db.get(SurveyType, survey_type_id)
        if survey_type is None:
            raise SurveyTypeTemplateError("Survey type not found")

        mapping = db.execute(
            select(SurveyTypeTemplate).where(
                SurveyTypeTemplate.survey_type_id == survey_type_id,
                SurveyTypeTemplate.template_id == int(template_id),
            )
        ).scalar_one_or_none()
        if mapping is None:
            raise SurveyTypeTemplateError("Template is not linked to this survey type")

        tpl = db.get(TelnyxWhatsappTemplate, int(template_id))
        if tpl is not None and not template_matches_survey_industry(
            tpl, survey_type, mapping=mapping
        ):
            raise SurveyTypeTemplateError("Template industry does not match survey type")

        db.delete(mapping)
        remaining = SurveyTypeTemplateService.linked_survey_type_count(db, int(template_id))
        if tpl is not None and remaining == 0 and str(tpl.telnyx_record_id or "").startswith("local-"):
            tpl.active_for_survey = False
            db.add(tpl)
        db.commit()
        return {
            "ok": True,
            "message": "Template removed from this survey type.",
            "template_id": int(template_id),
            "survey_type_id": survey_type_id,
        }

    @staticmethod
    def prune_stale_step_bank_mappings(
        db: Session,
        *,
        survey_type_id: str,
        keep_template_ids: list[int],
        privacy_mode: str | None = None,
    ) -> int:
        """Drop step-bank mappings for this survey type that are not in the latest saved pack."""
        keep = {int(tid) for tid in keep_template_ids}
        target_privacy = normalize_privacy_mode(privacy_mode) if privacy_mode else None
        survey_type = db.get(SurveyType, survey_type_id)
        if survey_type is None:
            return 0
        removed = 0
        for mapping in SurveyTypeTemplateService.list_for_survey_type(db, survey_type_id):
            if mapping.template_id in keep:
                continue
            row = db.get(TelnyxWhatsappTemplate, mapping.template_id)
            if row is None or not row.step_role:
                continue
            if not template_belongs_to_survey_type(row, survey_type):
                continue
            if target_privacy is not None:
                row_pm = resolve_row_privacy_mode(row)
                map_pm = resolve_mapping_privacy_mode(mapping, template_row=row)
                if row_pm != target_privacy or map_pm != target_privacy:
                    continue
            db.delete(mapping)
            removed += 1
        if removed:
            db.commit()
        return removed

    @staticmethod
    def cleanup_mistaken_links(db: Session, *, survey_type_id: str | None = None, dry_run: bool = False) -> dict[str, int]:
        """Remove survey_type_templates rows where the template name/owner does not match the survey type."""
        query = select(SurveyTypeTemplate)
        if survey_type_id:
            query = query.where(SurveyTypeTemplate.survey_type_id == survey_type_id)
        removed = 0
        scanned = 0
        for mapping in db.execute(query).scalars().all():
            scanned += 1
            st = db.get(SurveyType, mapping.survey_type_id)
            row = db.get(TelnyxWhatsappTemplate, mapping.template_id)
            if st is None or row is None:
                continue
            if template_belongs_to_survey_type(row, st):
                continue
            removed += 1
            if not dry_run:
                db.delete(mapping)
        if removed and not dry_run:
            db.commit()
        return {"scanned": scanned, "removed": removed, "dry_run": dry_run}

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
        privacy_mode: str | None = None,
    ) -> SurveyTypeTemplate:
        try:
            survey_type = db.get(SurveyType, survey_type_id)
            if survey_type is None:
                raise SurveyTypeTemplateError("Survey type not found")
            industry_id = resolve_survey_type_industry_id(survey_type)
            tpl = db.get(TelnyxWhatsappTemplate, template_id)
            if tpl is None:
                raise SurveyTypeTemplateError("Template not found")
            assert_industry_match(
                expected_industry_id=industry_id,
                actual_industry_id=getattr(tpl, "industry_id", None),
                message="Cannot link a template from a different industry",
            )
            apply_industry_to_template(tpl, survey_type)
        except SurveyIndustryScopeError as exc:
            raise SurveyTypeTemplateError(str(exc)) from exc

        if usable_as_anonymous and not usable_as_standard:
            resolved_privacy = normalize_privacy_mode(PRIVACY_MODE_ON if privacy_mode is None else privacy_mode)
        elif usable_as_standard and not usable_as_anonymous:
            resolved_privacy = normalize_privacy_mode(PRIVACY_MODE_OFF if privacy_mode is None else privacy_mode)
        else:
            resolved_privacy = normalize_privacy_mode(privacy_mode)
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
                industry_id=industry_id,
                survey_type_id=survey_type_id,
                template_id=template_id,
                created_at=now,
                updated_at=now,
            )
            db.add(row)

        row.industry_id = industry_id
        row.usable_as_standard = bool(usable_as_standard)
        row.usable_as_anonymous = bool(usable_as_anonymous)
        row.is_default_standard = bool(is_default_standard)
        row.is_default_anonymous = bool(is_default_anonymous)
        row.privacy_mode = resolved_privacy
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

        tpl = db.get(TelnyxWhatsappTemplate, template_id)
        if tpl is None:
            raise SurveyTypeTemplateError("Template not found")

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
            try:
                row = SurveyTypeTemplateService.upsert_mapping(
                    db,
                    survey_type_id=stid,
                    template_id=template_id,
                    usable_as_standard=usable_standard or is_default_standard,
                    usable_as_anonymous=usable_anonymous or is_default_anonymous,
                    is_default_standard=is_default_standard,
                    is_default_anonymous=is_default_anonymous,
                )
            except SurveyTypeTemplateError as exc:
                if "removed" not in str(exc).lower():
                    raise
                continue
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

        survey_type = db.get(SurveyType, survey_type_id)

        def pick(pool: list[SurveyTypeTemplate]) -> TelnyxWhatsappTemplate | None:
            templates: list[TelnyxWhatsappTemplate] = []
            for mapping in pool:
                tpl = db.get(TelnyxWhatsappTemplate, mapping.template_id)
                if tpl is None or not tpl.active_for_survey:
                    continue
                if survey_type is not None and not template_matches_survey_industry(tpl, survey_type, mapping=mapping):
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
