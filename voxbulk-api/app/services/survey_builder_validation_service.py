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
from app.services.survey_type_template_service import SurveyTypeTemplateService

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
    def _assert_meta_sendable(
        db: Session,
        tpl: TelnyxWhatsappTemplate,
        label: str,
        errors: list[str],
    ) -> None:
        from app.services.survey_whatsapp_template_service import (
            resolve_sendable_template_row,
            template_row_is_sendable_on_meta,
        )

        sendable = resolve_sendable_template_row(db, tpl)
        if sendable is None or not template_row_is_sendable_on_meta(sendable):
            errors.append(
                f"{label} template “{tpl.display_name or tpl.name}” is not approved on Meta yet "
                f"(status: {tpl.status}). Sync in Admin and wait for approval before launch."
            )

    @staticmethod
    def validate_order_config_for_launch(
        db: Session,
        config: dict[str, Any],
        *,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        """Block launch when welcome, thank-you, or middle steps are not Meta-sendable."""
        from app.services.survey_builder_runtime_service import load_builder_runtime

        runtime = load_builder_runtime(config) or {}
        industry_id = str(runtime.get("industry_id") or config.get("industry_id") or "").strip()
        type_ids = list(runtime.get("selected_survey_type_ids") or config.get("selected_survey_type_ids") or [])
        if not type_ids and config.get("survey_type_id"):
            type_ids = [str(config.get("survey_type_id"))]
        welcome_id = runtime.get("welcome_template_id") or config.get("welcome_template_id")
        thank_id = runtime.get("thank_you_template_id") or config.get("thank_you_template_id")
        middle_map = runtime.get("selected_service_template_ids") or config.get("selected_service_template_ids")
        middle_list = runtime.get("ordered_middle_template_ids") or config.get("selected_middle_template_ids")
        return SurveyBuilderValidationService.validate_builder_selection(
            db,
            industry_id=industry_id,
            selected_survey_type_ids=type_ids,
            welcome_template_id=welcome_id,
            thank_you_template_id=thank_id,
            selected_service_template_ids=middle_map,
            selected_middle_template_ids=middle_list,
            require_approved=True,
            allow_final_additional_feedback=bool(config.get("allow_final_additional_feedback")),
            privacy_mode=config.get("privacy_mode"),
            anonymous_responses=bool(config.get("anonymous_responses")),
            org_id=org_id,
        )

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
        from app.services.survey_whatsapp_template_service import template_row_is_sendable_on_meta

        mappings = SurveyTypeTemplateService.list_for_survey_type(db, survey_type_id)
        for mapping in mappings:
            row = db.get(TelnyxWhatsappTemplate, mapping.template_id)
            if row is None or not bool(row.active_for_survey):
                continue
            if template_row_is_sendable_on_meta(row):
                return True
        return False

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
        allow_final_additional_feedback: bool = False,
        privacy_mode: str | None = None,
        anonymous_responses: bool = False,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        errors: list[str] = []
        industry = db.get(Industry, str(industry_id or "").strip())
        if industry is None or not industry.is_active or bool(getattr(industry, "is_hidden", False)):
            errors.append("Select a valid industry.")
        elif org_id:
            from app.services.industry_service import IndustryService

            if not IndustryService._industry_visible_to_org(db, industry, org_id):
                errors.append("This industry is not available for your organisation.")
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
            if tpl is None:
                errors.append(f"{label} template not found.")
                continue
            if not tpl.active_for_survey:
                errors.append(f"{label} template is hidden in Admin — select another.")
                continue
            if not SurveySystemTemplateService.is_builder_listed_system_template_id(db, tpl_int, kind):
                if SurveySystemTemplateService.template_mapped_to_system_kind(db, tpl_int, kind):
                    errors.append(f"{label} template is hidden in Admin — select another.")
                else:
                    errors.append(f"{label} template must be from system {kind} templates.")
                continue
            if require_approved:
                SurveyBuilderValidationService._assert_meta_sendable(db, tpl, label, errors)
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
                    if require_approved:
                        SurveyBuilderValidationService._assert_meta_sendable(
                            db,
                            tpl,
                            st.name if st else type_id,
                            errors,
                        )
        tell_us_more_id = None
        if not errors:
            try:
                tell_us_more_id = SurveySystemTemplateService.resolve_tell_us_more_template_id(
                    db,
                    {
                        "privacy_mode": privacy_mode,
                        "anonymous_responses": anonymous_responses,
                    },
                )
            except Exception:
                tell_us_more_id = None
        if errors:
            raise SurveyBuilderValidationError(errors[0], errors=errors)

        def _tpl_int(raw: Any, label: str) -> int | None:
            if raw is None or raw == "":
                return None
            try:
                return int(raw)
            except (TypeError, ValueError) as exc:
                raise SurveyBuilderValidationError(f"{label} template id is invalid.") from exc

        return {
            "ok": True,
            "industry_id": industry.id if industry else None,
            "selected_survey_type_ids": ids,
            "primary_survey_type_id": ids[0] if ids else None,
            "welcome_template_id": _tpl_int(welcome_template_id, "Welcome"),
            "thank_you_template_id": _tpl_int(thank_you_template_id, "Thank-you"),
            "tell_us_more_template_id": tell_us_more_id,
            "ordered_middle_template_ids": [tpl_id for _, tpl_id in middle_pairs],
            "builder_page_count": len(middle_pairs) + 2 if middle_pairs else None,
            "allow_final_additional_feedback": bool(allow_final_additional_feedback),
        }
