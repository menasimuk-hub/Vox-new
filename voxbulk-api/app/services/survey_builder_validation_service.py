"""Server-side validation for dashboard WA survey builder selections."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_system_template_service import SYSTEM_TEMPLATE_KINDS, SurveySystemTemplateService

MIN_SERVICE_TAGS = 1
MAX_SERVICE_TAGS = 4
MIN_TEMPLATE_COUNT = 1
MAX_TEMPLATE_COUNT = 50


class SurveyBuilderValidationError(ValueError):
    def __init__(self, message: str, *, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


class SurveyBuilderValidationService:
    @staticmethod
    def resolve_middle_template_source(
        selected_survey_type_ids: list[str],
        *,
        selected_service_template_ids: Any = None,
        selected_middle_template_ids: Any = None,
    ) -> Any | None:
        """Prefer type→template map; fall back to ordered middle template id list."""
        ids = [str(x).strip() for x in (selected_survey_type_ids or []) if str(x).strip()]
        if isinstance(selected_service_template_ids, dict) and selected_service_template_ids:
            return selected_service_template_ids
        if isinstance(selected_service_template_ids, list) and selected_service_template_ids:
            return selected_service_template_ids
        if selected_middle_template_ids is not None:
            if isinstance(selected_middle_template_ids, dict) and selected_middle_template_ids:
                return selected_middle_template_ids
            if isinstance(selected_middle_template_ids, list) and selected_middle_template_ids:
                if ids and len(selected_middle_template_ids) == len(ids):
                    return selected_middle_template_ids
                pairs = SurveyBuilderValidationService.parse_middle_template_pairs(
                    ids, selected_middle_template_ids
                )
                if pairs:
                    return selected_middle_template_ids
                return selected_middle_template_ids
        if selected_service_template_ids is not None:
            return selected_service_template_ids
        return None

    @staticmethod
    def parse_middle_template_pairs(
        selected_survey_type_ids: list[str],
        raw: Any,
    ) -> list[tuple[str, int]]:
        ids = [str(x).strip() for x in (selected_survey_type_ids or []) if str(x).strip()]
        if not raw:
            return []
        if isinstance(raw, dict):
            pairs: list[tuple[str, int]] = []
            for type_id in ids:
                value = raw.get(type_id)
                if value is None:
                    value = raw.get(str(type_id))
                if value is not None and str(value).strip():
                    try:
                        pairs.append((type_id, int(value)))
                    except (TypeError, ValueError):
                        continue
            return pairs
        if isinstance(raw, list):
            if raw and isinstance(raw[0], dict):
                by_type: dict[str, int] = {}
                for item in raw:
                    type_key = str(item.get("survey_type_id") or item.get("type_id") or "").strip()
                    if not type_key or item.get("template_id") is None:
                        continue
                    try:
                        by_type[type_key] = int(item.get("template_id"))
                    except (TypeError, ValueError):
                        continue
                return [(type_id, by_type[type_id]) for type_id in ids if type_id in by_type]
            ints: list[int] = []
            for x in raw:
                if x is None or not str(x).strip():
                    continue
                try:
                    ints.append(int(x))
                except (TypeError, ValueError):
                    continue
            if ints and not ids:
                return [(str(i), tid) for i, tid in enumerate(ints)]
            if len(ints) == len(ids):
                return [(type_id, template_id) for type_id, template_id in zip(ids, ints)]
        return []

    @staticmethod
    def clamp_template_count(raw: int | str | None) -> int:
        if raw is None or raw == "":
            value = 5
        else:
            try:
                value = int(raw)
            except (TypeError, ValueError):
                value = 5
        return max(MIN_TEMPLATE_COUNT, min(MAX_TEMPLATE_COUNT, value))

    @staticmethod
    def _type_has_wa_template(db: Session, survey_type_id: str) -> bool:
        count = int(
            db.execute(
                select(func.count())
                .select_from(SurveyTypeTemplate)
                .join(TelnyxWhatsappTemplate, TelnyxWhatsappTemplate.id == SurveyTypeTemplate.template_id)
                .where(
                    SurveyTypeTemplate.survey_type_id == survey_type_id,
                    TelnyxWhatsappTemplate.active_for_survey.is_(True),
                )
            ).scalar_one()
            or 0
        )
        return count > 0

    @staticmethod
    def validate_builder_selection(
        db: Session,
        *,
        industry_id: str,
        selected_survey_type_ids: list[str],
        welcome_template_id: int | str | None,
        thank_you_template_id: int | str | None,
        selected_service_template_ids: Any = None,
        selected_middle_template_ids: Any = None,
        require_approved: bool = False,
    ) -> dict[str, Any]:
        errors: list[str] = []
        industry = db.get(Industry, str(industry_id or "").strip())
        if industry is None or not industry.is_active or bool(getattr(industry, "is_hidden", False)):
            errors.append("Select a valid industry.")
        ids = [str(x).strip() for x in (selected_survey_type_ids or []) if str(x).strip()]
        if len(ids) < MIN_SERVICE_TAGS:
            errors.append(f"Select at least {MIN_SERVICE_TAGS} service tag.")
        if len(ids) > MAX_SERVICE_TAGS:
            errors.append(f"Select at most {MAX_SERVICE_TAGS} service tags.")
        if len(ids) != len(set(ids)):
            errors.append("Duplicate service tags are not allowed.")
        for tid in ids:
            st = db.get(SurveyType, tid)
            if st is None or not st.is_active:
                errors.append(f"Service tag not found: {tid}")
                continue
            if industry is not None and st.industry_id != industry.id:
                errors.append(f"“{st.name}” does not belong to the selected industry.")
                continue
            if st.system_template_kind:
                errors.append(f"“{st.name}” is a system template, not a service tag.")
                continue
            if not SurveyBuilderValidationService._type_has_wa_template(db, st.id):
                errors.append(f"“{st.name}” has no WhatsApp template — create one in Admin first.")
        if not welcome_template_id:
            errors.append("Welcome template is required.")
        if not thank_you_template_id:
            errors.append("Thank-you template is required.")
        for label, tpl_id, kind in (
            ("Welcome", welcome_template_id, "welcome"),
            ("Thank-you", thank_you_template_id, "thank_you"),
        ):
            if not tpl_id:
                continue
            try:
                tpl_int = int(tpl_id)
            except (TypeError, ValueError):
                errors.append(f"{label} template id is invalid.")
                continue
            tpl = db.get(TelnyxWhatsappTemplate, tpl_int)
            if tpl is None or not tpl.active_for_survey:
                errors.append(f"{label} template not found.")
                continue
            st = db.get(SurveyType, str(tpl.survey_type_id or ""))
            if st is None or st.system_template_kind != kind:
                errors.append(f"{label} template must be from system {kind} templates.")
                continue
            if require_approved and str(tpl.status or "").upper() not in {"APPROVED", "LOCAL_DRAFT"}:
                errors.append(f"{label} template is not ready yet (status: {tpl.status}).")
        middle_pairs: list[tuple[str, int]] = []
        if welcome_template_id and thank_you_template_id and ids:
            middle_source = SurveyBuilderValidationService.resolve_middle_template_source(
                ids,
                selected_service_template_ids=selected_service_template_ids,
                selected_middle_template_ids=selected_middle_template_ids,
            )
            if middle_source is None:
                errors.append("Select a library template for each survey type in Step 3.")
            else:
                middle_pairs = SurveyBuilderValidationService.parse_middle_template_pairs(ids, middle_source)
                if len(middle_pairs) < len(ids):
                    missing = [tid for tid in ids if tid not in {pair[0] for pair in middle_pairs}]
                    for type_id in missing:
                        st = db.get(SurveyType, type_id)
                        label = st.name if st is not None else type_id
                        errors.append(f"Select a template for \"{label}\".")
                for type_id, tpl_id in middle_pairs:
                    st = db.get(SurveyType, type_id)
                    tpl = db.get(TelnyxWhatsappTemplate, tpl_id)
                    if tpl is None or not tpl.active_for_survey:
                        errors.append(f"Template not found for \"{st.name if st else type_id}\".")
                        continue
                    linked = db.execute(
                        select(SurveyTypeTemplate).where(
                            SurveyTypeTemplate.survey_type_id == type_id,
                            SurveyTypeTemplate.template_id == tpl_id,
                        )
                    ).scalar_one_or_none()
                    if linked is None:
                        errors.append(
                            f"Template for \"{st.name if st else type_id}\" is not linked to that survey type."
                        )
                        continue
                    role = str(tpl.step_role or "").strip().lower()
                    if role in {"start", "completion", "intro", "closing"}:
                        errors.append(
                            f"\"{st.name if st else type_id}\" template must be a survey question, not welcome/thank-you."
                        )
        tell_us_more_id = None
        if not errors:
            tell_us_more_id = SurveySystemTemplateService.resolve_tell_us_more_template_id(db)
        if errors:
            raise SurveyBuilderValidationError(errors[0], errors=errors)
        return {
            "ok": True,
            "industry_id": industry.id if industry else None,
            "selected_survey_type_ids": ids,
            "primary_survey_type_id": ids[0] if ids else None,
            "welcome_template_id": int(welcome_template_id) if welcome_template_id else None,
            "thank_you_template_id": int(thank_you_template_id) if thank_you_template_id else None,
            "tell_us_more_template_id": tell_us_more_id,
            "ordered_middle_template_ids": [tpl_id for _, tpl_id in middle_pairs],
            "builder_page_count": len(middle_pairs) + 2 if middle_pairs else None,
        }
