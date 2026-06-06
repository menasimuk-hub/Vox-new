"""WA Survey template cleanup and Utility category helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import SYSTEM_SURVEY_INDUSTRY_SLUG
from app.services.survey_system_template_service import SYSTEM_TEMPLATE_KINDS
from app.services.survey_type_template_service import SurveyTypeTemplateService
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncError,
    TelnyxWhatsappTemplateSyncService,
)

KEEP_INDUSTRY_SLUGS = frozenset({SYSTEM_SURVEY_INDUSTRY_SLUG, "hospitality_food"})
WA_TEMPLATE_DEFAULT_CATEGORY = "UTILITY"


def _industry_slug(db: Session, industry_id: str | None) -> str | None:
    if not industry_id:
        return None
    row = db.get(Industry, industry_id)
    return str(row.slug or "").strip() if row else None


def template_should_keep(db: Session, tpl: TelnyxWhatsappTemplate) -> bool:
    """Keep Global System Templates and Hospitality & food WA Survey templates only."""
    slug = _industry_slug(db, tpl.industry_id)
    if slug in KEEP_INDUSTRY_SLUGS:
        return True

    if tpl.survey_type_id:
        st = db.get(SurveyType, str(tpl.survey_type_id))
        if st is not None:
            if str(st.system_template_kind or "") in SYSTEM_TEMPLATE_KINDS:
                return True
            st_slug = _industry_slug(db, st.industry_id)
            if st_slug in KEEP_INDUSTRY_SLUGS:
                return True

    for mapping in SurveyTypeTemplateService.list_for_template(db, int(tpl.id)):
        st = db.get(SurveyType, str(mapping.survey_type_id))
        if st is None:
            continue
        if str(st.system_template_kind or "") in SYSTEM_TEMPLATE_KINDS:
            return True
        if _industry_slug(db, st.industry_id) in KEEP_INDUSTRY_SLUGS:
            return True
        if _industry_slug(db, mapping.industry_id) in KEEP_INDUSTRY_SLUGS:
            return True

    return False


def cleanup_wa_survey_templates(
    db: Session,
    *,
    dry_run: bool = True,
    update_category_to_utility: bool = True,
) -> dict[str, Any]:
    """
    Delete WA Survey templates outside Global System Templates + Hospitality & food.
    Optionally set kept templates to UTILITY category.
    """
    rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars())
    kept: list[dict[str, Any]] = []
    deleted: list[dict[str, Any]] = []
    warnings: list[str] = []
    category_updates = 0

    for tpl in rows:
        keep = template_should_keep(db, tpl)
        summary = {
            "id": int(tpl.id),
            "name": tpl.name,
            "display_name": tpl.display_name,
            "industry_id": tpl.industry_id,
            "survey_type_id": tpl.survey_type_id,
            "step_role": tpl.step_role,
            "category": tpl.category,
        }
        if keep:
            kept.append(summary)
            if update_category_to_utility and str(tpl.category or "").upper() != WA_TEMPLATE_DEFAULT_CATEGORY:
                if not dry_run:
                    tpl.category = WA_TEMPLATE_DEFAULT_CATEGORY
                    db.add(tpl)
                category_updates += 1
            continue

        if dry_run:
            deleted.append(summary)
            continue

        record_id = str(tpl.telnyx_record_id or "").strip()
        if record_id and not record_id.startswith("local-"):
            try:
                TelnyxWhatsappTemplateSyncService.delete_remote_template(db, record_id)
            except TelnyxWhatsappTemplateSyncError as exc:
                warnings.append(f"{tpl.name}: Telnyx delete failed ({exc})")

        for mapping in SurveyTypeTemplateService.list_for_template(db, int(tpl.id)):
            db.delete(mapping)
        db.delete(tpl)
        deleted.append(summary)

    if not dry_run:
        db.commit()

    return {
        "ok": True,
        "dry_run": dry_run,
        "keep_industry_slugs": sorted(KEEP_INDUSTRY_SLUGS),
        "total_scanned": len(rows),
        "kept_count": len(kept),
        "deleted_count": len(deleted),
        "category_updates": category_updates,
        "kept": kept,
        "deleted": deleted,
        "warnings": warnings,
    }
