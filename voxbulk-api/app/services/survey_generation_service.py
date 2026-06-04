"""Generate survey flows using WA Survey step bank (4–6 pages)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.service_script_generator import generate_survey_script
from app.services.survey_step_bank_service import (
    SurveyStepBankService,
    page_count_from_length,
)
from app.services.survey_type_service import SurveyTypeService
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
        count = page_count_from_length(page_count if page_count is not None else length_key)

        try:
            composed = SurveyStepBankService.compose_survey(
                db,
                survey_type=survey_type,
                variant=variant_key,
                privacy_mode=resolved_privacy,
                page_count=count,
                auto_select=auto_select_steps,
                selected_step_roles=selected_step_roles,
            )
        except ValueError as e:
            raise ValueError(str(e)) from e

        start_id = composed.get("start_template_id")
        if not start_id:
            raise ValueError(
                f"No start template in the step bank for {survey_type.name}. "
                "Generate and save a 10-template pack in Admin → WA Survey."
            )
        start_row = db.get(TelnyxWhatsappTemplate, int(start_id))
        if start_row is None:
            raise ValueError("Start template not found in step bank")
        if str(start_row.status or "").upper() != "APPROVED":
            raise ValueError(
                f"Start template “{start_row.display_name or start_row.name}” is not APPROVED yet "
                f"(status: {start_row.status}). Push to Telnyx and wait for Meta approval."
            )

        preview = composed.get("template_preview") or SurveyWhatsappTemplateService.build_preview(
            db,
            start_row,
            business_name=client_name or organisation_name,
        )
        middle_questions = composed["whatsapp_flow"]["questions"]
        question_texts = [
            str(q.get("text") or q) if isinstance(q, dict) else str(q) for q in middle_questions
        ]
        closing = str(composed.get("completion_body") or "Thank you — your feedback helps us improve.")
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
                },
            )
        except Exception:
            script_result = {}

        wa_questions = script_result.get("whatsapp_questions")
        if isinstance(wa_questions, list) and wa_questions:
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

        return {
            "ok": True,
            "survey_type": {
                "id": survey_type.id,
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
                + [f"{i + 1}. [{p['step_role']}] {p.get('body', '')[:120]}" for i, p in enumerate(composed["pages"])]
                + ["", "CLOSING", closing]
            ),
            "system_prompt": script_result.get("system_prompt") or "",
        }

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
        return errors
