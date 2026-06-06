"""Generate survey flows using WA Survey step bank (4–6 pages)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.service_script_generator import generate_survey_script
from app.services.survey_step_bank_service import (
    SurveyStepBankService,
    builder_page_count,
    page_count_from_length,
)
from app.services.survey_flow_config_service import attach_flow_to_config, flow_engine as resolve_flow_engine, max_question_visits
from app.services.survey_tell_us_more_flow_service import (
    attach_tell_us_more_graph,
    inject_reason_step_into_composed,
)
from app.services.survey_builder_flow_service import (
    build_builder_step_sequence,
    build_builder_template_ids,
    builder_generation_config,
)
from app.services.survey_builder_runtime_service import (
    attach_builder_runtime_to_config,
    build_builder_runtime,
)
from app.services.survey_flow_constants import FLOW_ENGINE_GRAPH, FLOW_ENGINE_LINEAR
from app.services.survey_flow_definition_service import SurveyFlowDefinitionService
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService
from app.services.wa_template_privacy import (
    VARIANT_ANONYMOUS,
    VARIANT_STANDARD,
    normalize_privacy_mode,
    privacy_mode_to_variant,
    variant_to_privacy_mode,
)


class SurveyGenerationService:
    @staticmethod
    def generate(
        db: Session,
        *,
        survey_type_id: str,
        variant: str = VARIANT_STANDARD,
        privacy_mode: str | None = None,
        length: str = "standard",
        page_count: int | None = None,
        auto_select_steps: bool = True,
        selected_step_roles: list[str] | None = None,
        goal: str = "",
        organisation_name: str = "Your business",
        client_name: str = "",
        assistant_name: str = "",
        organiser_name: str = "",
        flow_engine: str | None = None,
        flow_definition_id: str | None = None,
        flow_branches: list[dict[str, Any]] | None = None,
        allow_unapproved_templates: bool = False,
        builder_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        survey_type = SurveyTypeService.get_type(db, survey_type_id)
        if survey_type is None or not survey_type.is_active:
            raise ValueError("Survey type not found or inactive")

        variant_key = str(variant or VARIANT_STANDARD).strip().lower()
        resolved_privacy = normalize_privacy_mode(privacy_mode) if privacy_mode else variant_to_privacy_mode(variant_key)
        variant_key = privacy_mode_to_variant(resolved_privacy)
        if variant_key == VARIANT_ANONYMOUS and not survey_type.supports_anonymous:
            raise ValueError("Anonymous surveys are not enabled for this survey type")

        length_key = str(length or survey_type.default_length or "standard").strip().lower()

        welcome_template_id = None
        thank_you_template_id = None
        tell_us_more_template_id = None
        selected_survey_type_ids: list[str] = []
        ordered_middle_template_ids: list[int] = []
        if builder_config:
            welcome_template_id = builder_config.get("welcome_template_id")
            thank_you_template_id = builder_config.get("thank_you_template_id")
            tell_us_more_template_id = builder_config.get("tell_us_more_template_id")
            selected_survey_type_ids = list(builder_config.get("selected_survey_type_ids") or [])
            ordered_middle_template_ids: list[int] = []
            for raw_id in builder_config.get("ordered_middle_template_ids") or []:
                if raw_id is None:
                    continue
                try:
                    ordered_middle_template_ids.append(int(raw_id))
                except (TypeError, ValueError):
                    continue

        if ordered_middle_template_ids:
            count = builder_page_count(len(ordered_middle_template_ids))
        else:
            count = page_count_from_length(page_count if page_count is not None else length_key)
            if builder_config and selected_survey_type_ids:
                count = builder_page_count(len(selected_survey_type_ids))

        try:
            composed = SurveyStepBankService.compose_survey(
                db,
                survey_type=survey_type,
                variant=variant_key,
                privacy_mode=resolved_privacy,
                page_count=count,
                auto_select=auto_select_steps,
                selected_step_roles=selected_step_roles,
                welcome_template_id=welcome_template_id,
                thank_you_template_id=thank_you_template_id,
                ordered_middle_template_ids=ordered_middle_template_ids or None,
            )
        except ValueError as e:
            raise ValueError(str(e)) from e

        start_id = welcome_template_id or composed.get("start_template_id")
        if not start_id:
            raise ValueError(
                f"No start template in the step bank for {survey_type.name}. "
                "Generate and save a template pack in Admin → WA Survey, or select a welcome template."
            )
        start_row = db.get(TelnyxWhatsappTemplate, int(start_id))
        if start_row is None:
            raise ValueError("Start template not found in step bank")
        start_status = str(start_row.status or "").upper()
        if start_status != "APPROVED" and not allow_unapproved_templates:
            raise ValueError(
                f"Start template “{start_row.display_name or start_row.name}” is not APPROVED yet "
                f"(status: {start_row.status}). Push to Telnyx and wait for Meta approval."
            )

        preview = composed.get("template_preview") or SurveyWhatsappTemplateService.build_preview(
            db,
            start_row,
            business_name=client_name or organisation_name,
        )
        if tell_us_more_template_id and not ordered_middle_template_ids:
            composed = inject_reason_step_into_composed(
                composed,
                tell_us_more_template_id=tell_us_more_template_id,
                db=db,
            )

        builder_step_sequence: list[dict[str, Any]] = []
        if ordered_middle_template_ids:
            builder_step_sequence = build_builder_step_sequence(
                db,
                middle_template_ids=ordered_middle_template_ids,
                business_name=client_name or organisation_name,
            )
            whatsapp_flow_seed = dict(composed.get("whatsapp_flow") or {})
            whatsapp_flow_seed["questions"] = builder_step_sequence
            composed = {**composed, "whatsapp_flow": whatsapp_flow_seed}

        middle_questions = composed["whatsapp_flow"]["questions"]
        question_texts = [
            str(q.get("text") or q) if isinstance(q, dict) else str(q) for q in middle_questions
        ]
        closing = str(composed.get("completion_body") or "Thank you — your feedback helps us improve.")
        if thank_you_template_id:
            thank_row = db.get(TelnyxWhatsappTemplate, int(thank_you_template_id))
            if thank_row is not None and thank_row.body_preview:
                closing = str(thank_row.body_preview)
        if variant_key == VARIANT_ANONYMOUS:
            closing = "Thank you — your anonymous feedback has been recorded."

        script_result: dict[str, Any] = {}
        try:
            script_result = generate_survey_script(
                db,
                goal=goal or survey_type.description or survey_type.name,
                contact_method="WhatsApp",
                max_call_length="3 minutes",
                organisation_name=organisation_name,
                assistant_name=assistant_name or organiser_name or client_name or organisation_name,
                organiser_name=organiser_name or client_name or organisation_name,
                client_name=client_name or organisation_name,
                terminology_label="customer",
                org_id=None,
                order_config={
                    "anonymous_responses": variant_key == VARIANT_ANONYMOUS,
                    "survey_type_id": survey_type.id,
                    "survey_type_slug": survey_type.slug,
                    "survey_length": length_key,
                    "page_count": count,
                    "page_roles": composed["page_roles"],
                    "wa_template_id": start_row.id,
                    "welcome_template_id": welcome_template_id,
                    "thank_you_template_id": thank_you_template_id,
                    "tell_us_more_template_id": tell_us_more_template_id,
                    "selected_survey_type_ids": selected_survey_type_ids,
                },
            )
        except Exception:
            script_result = {}

        wa_questions = script_result.get("whatsapp_questions")
        if isinstance(wa_questions, list) and wa_questions and not ordered_middle_template_ids:
            ai_texts = [
                str(q.get("text") or q) if isinstance(q, dict) else str(q) for q in wa_questions
            ]
            for idx, text in enumerate(ai_texts[: len(question_texts)]):
                if text.strip():
                    question_texts[idx] = text.strip()
                    if idx < len(middle_questions) and isinstance(middle_questions[idx], dict):
                        middle_questions[idx]["text"] = text.strip()

        whatsapp_flow = {
            **composed["whatsapp_flow"],
            "questions": middle_questions,
            "closing": closing,
        }

        engine_key = resolve_flow_engine({"flow_engine": flow_engine} if flow_engine else {})
        flow_snapshot = None
        resolved_flow_definition_id = None
        order_config_extras: dict[str, Any] = {}
        mq = max_question_visits(
            {"page_count": count},
            survey_type_max_length=survey_type.max_length,
        )
        builder_runtime: dict[str, Any] | None = None
        if ordered_middle_template_ids:
            builder_runtime = build_builder_runtime(
                db,
                industry_id=(builder_config or {}).get("industry_id"),
                survey_type_id=survey_type.id,
                survey_type_name=survey_type.name,
                privacy_mode=resolved_privacy,
                welcome_template_id=welcome_template_id or start_row.id,
                middle_template_ids=ordered_middle_template_ids,
                tell_us_more_template_id=tell_us_more_template_id,
                thank_you_template_id=thank_you_template_id,
                business_name=client_name or organisation_name,
            )
            order_config_extras = attach_builder_runtime_to_config({}, builder_runtime)
            builder_step_sequence = builder_runtime["step_sequence"]
            whatsapp_flow = attach_builder_runtime_to_config(
                {**whatsapp_flow, "closing": closing},
                builder_runtime,
            )
            engine_key = FLOW_ENGINE_LINEAR
            flow_snapshot = None
            resolved_flow_definition_id = None
        elif tell_us_more_template_id:
            order_config_extras = attach_tell_us_more_graph(
                composed=composed,
                survey_type_id=survey_type.id,
                privacy_mode=resolved_privacy,
                page_count=count,
                closing_body=closing,
                max_question_visits=mq,
                flow_definition_id=flow_definition_id,
            )
            flow_snapshot = order_config_extras.get("flow_snapshot")
            resolved_flow_definition_id = order_config_extras.get("flow_definition_id")
            engine_key = FLOW_ENGINE_GRAPH
        elif engine_key == FLOW_ENGINE_GRAPH:
            draft_config = {
                "survey_type_id": survey_type.id,
                "privacy_mode": resolved_privacy,
                "page_count": count,
                "page_roles": composed["page_roles"],
                "flow_definition_id": flow_definition_id,
                "flow_branches": flow_branches,
            }
            flow_snapshot, resolved_flow_definition_id = SurveyFlowDefinitionService.resolve_snapshot_for_order(
                db,
                config=draft_config,
                survey_type=survey_type,
                questions=middle_questions,
                page_roles=composed["page_roles"],
                closing_body=closing,
            )
            order_config_extras = attach_flow_to_config(
                draft_config,
                snapshot=flow_snapshot,
                flow_definition_id=resolved_flow_definition_id,
            )

        result_payload = {
            "ok": True,
            "survey_type": {
                "id": survey_type.id,
                "industry_id": survey_type.industry_id,
                "slug": survey_type.slug,
                "name": survey_type.name,
            },
            "variant": variant_key,
            "privacy_mode": resolved_privacy,
            "length": length_key,
            "page_count": count,
            "question_count": len(question_texts),
            "page_roles": composed["page_roles"],
            "pages": composed["pages"],
            "anonymous_responses": variant_key == VARIANT_ANONYMOUS,
            "allow_follow_up": variant_key != VARIANT_ANONYMOUS,
            "auto_select_steps": auto_select_steps,
            "wa_template_id": start_row.id,
            "welcome_template_id": welcome_template_id,
            "thank_you_template_id": thank_you_template_id,
            "tell_us_more_template_id": tell_us_more_template_id,
            "selected_survey_type_ids": selected_survey_type_ids,
            "wa_template_name": start_row.name,
            "wa_template_send_id": start_row.template_id,
            "template_preview": preview,
            "questions": question_texts,
            "flow_steps": composed["flow_steps"],
            "whatsapp_flow": whatsapp_flow,
            "step_bank_available": composed.get("step_bank_available") or [],
            "step_bank_missing": composed.get("step_bank_missing") or [],
            "approved_script": script_result.get("script_text") or "\n".join(
                ["INTRO", preview.get("rendered_body") or "", "", "PAGES"]
                + [
                    f"{i + 1}. [{p.get('step_role', '?')}] {str(p.get('body', ''))[:120]}"
                    for i, p in enumerate(composed.get("pages") or [])
                ]
                + ["", "CLOSING", closing]
            ),
            "system_prompt": script_result.get("system_prompt") or "",
            "flow_engine": engine_key,
            "flow_definition_id": resolved_flow_definition_id,
            "flow_snapshot": flow_snapshot,
            "builder_step_sequence": builder_step_sequence or None,
            "builder_template_ids": build_builder_template_ids(
                welcome_template_id=welcome_template_id or start_row.id,
                middle_template_ids=ordered_middle_template_ids,
                thank_you_template_id=thank_you_template_id,
                tell_us_more_template_id=tell_us_more_template_id,
            )
            or None,
            "builder_runtime": builder_runtime,
            "builder_runtime_hash": builder_runtime.get("hash") if builder_runtime else None,
        }
        if order_config_extras:
            result_payload["order_config_flow"] = {
                **order_config_extras,
                "builder_step_sequence": builder_step_sequence or None,
                "builder_template_ids": result_payload.get("builder_template_ids"),
            }
        return result_payload

    @staticmethod
    def validate_order_config(config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if str(config.get("delivery") or "").lower() != "whatsapp" and "whatsapp" not in str(
            config.get("contact_method") or ""
        ).lower():
            return errors
        if not config.get("survey_type_id"):
            errors.append("Survey type is required for WhatsApp surveys")
        if not config.get("wa_template_id") and not config.get("survey_type_id"):
            errors.append("WhatsApp template is required")
        page_count = config.get("page_count")
        if page_count is not None:
            try:
                pc = int(page_count)
                if pc < 4 or pc > 6:
                    errors.append("WhatsApp surveys must be 4–6 pages")
            except (TypeError, ValueError):
                errors.append("page_count must be an integer between 4 and 6")
        if resolve_flow_engine(config) == FLOW_ENGINE_GRAPH:
            from app.services.survey_flow_config_service import get_flow_snapshot
            from app.services.survey_flow_compiler_service import validate_flow_snapshot

            snap = get_flow_snapshot(config)
            if not snap:
                errors.append("flow_engine=graph requires flow_snapshot on order config")
            else:
                errors.extend(validate_flow_snapshot(snap))
        return errors
