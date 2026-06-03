"""Generate survey flows using WA Survey template library."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.service_script_generator import generate_survey_script
from app.services.survey_type_service import LENGTH_OPTIONS, SurveyTypeService
from app.services.survey_whatsapp_template_service import (
    VARIANT_ANONYMOUS,
    VARIANT_STANDARD,
    SurveyWhatsappTemplateService,
)

QUESTION_BANK: dict[str, list[str]] = {
    "customer_satisfaction": [
        "On a scale of 0-10, how likely are you to recommend us to a friend?",
        "What did we do well on your recent visit?",
        "What is one thing we could improve?",
        "How satisfied were you with the overall experience?",
        "Would you use our services again?",
        "Any other comments for our team?",
    ],
    "service_quality": [
        "How would you rate the quality of service you received?",
        "Was our team friendly and professional?",
        "Did we resolve your request in good time?",
        "How clear was our communication?",
        "What could we do better next time?",
        "Anything else we should know?",
    ],
    "price_value": [
        "How fair did you find our pricing?",
        "Did you feel you received good value for money?",
        "How does our pricing compare to alternatives you know?",
        "Would clearer pricing information help?",
        "What would make our offer feel better value?",
        "Any other pricing feedback?",
    ],
    "complaint_followup": [
        "Was your complaint resolved to your satisfaction?",
        "How would you rate our follow-up communication?",
        "Do you feel we took your concern seriously?",
        "Is there anything still outstanding?",
        "How likely are you to use us again after this follow-up?",
        "Any final comments?",
    ],
    "quick_feedback": [
        "How was your experience today?",
        "What went well?",
        "What could be better?",
        "Would you recommend us?",
        "Rate our service from 1-5.",
        "Any quick comments?",
    ],
}


def _simulated_flow_steps(
    *,
    questions: list[str],
    variant: str,
    closing: str,
    buttons: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {
            "step": 1,
            "kind": "template_outbound",
            "title": "Approved WhatsApp template",
            "description": "First business-initiated message sent via Telnyx template.",
        }
    ]
    if buttons:
        steps.append(
            {
                "step": 2,
                "kind": "user_action",
                "title": f"Recipient taps “{buttons[0].get('label', 'Start survey')}”",
                "description": "Simulated button tap opens the session window.",
            }
        )
    offset = len(steps)
    for i, question in enumerate(questions, start=1):
        steps.append(
            {
                "step": offset + i,
                "kind": "survey_question",
                "title": f"Question {i}",
                "body": question,
                "description": "Simulated free-form or quick-reply follow-up message.",
            }
        )
    steps.append(
        {
            "step": offset + len(questions) + 1,
            "kind": "closing",
            "title": "Thank you",
            "body": closing,
            "description": "Simulated closing message.",
        }
    )
    if variant == VARIANT_ANONYMOUS:
        for step in steps:
            step["anonymous"] = True
    return steps[:8]


class SurveyGenerationService:
    @staticmethod
    def generate(
        db: Session,
        *,
        survey_type_id: str,
        variant: str = VARIANT_STANDARD,
        length: str = "standard",
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
        if variant_key == VARIANT_ANONYMOUS and not survey_type.supports_anonymous:
            raise ValueError("Anonymous surveys are not enabled for this survey type")

        length_key = str(length or survey_type.default_length or "standard").strip().lower()
        question_count = LENGTH_OPTIONS.get(length_key, SurveyTypeService.question_count_for_length(length_key))

        template = SurveyWhatsappTemplateService.resolve_for_survey(
            db,
            survey_type_id=survey_type.id,
            variant=variant_key,
        )
        if template is None:
            raise ValueError(
                f"No WhatsApp template configured for {survey_type.name} ({variant_key}). "
                "Create and approve a template in Admin → Platform Settings → WA Survey."
            )
        if str(template.status or "").upper() != "APPROVED":
            raise ValueError(
                f"Template “{template.display_name or template.name}” is not APPROVED yet "
                f"(status: {template.status}). Push to Telnyx and wait for Meta approval."
            )

        bank = QUESTION_BANK.get(survey_type.slug, QUESTION_BANK["quick_feedback"])
        questions = bank[:question_count]
        while len(questions) < question_count:
            questions.append(f"Please share any additional feedback (question {len(questions) + 1}).")

        preview = SurveyWhatsappTemplateService.build_preview(
            db,
            template,
            business_name=client_name or organisation_name,
        )
        closing = "Thank you — your feedback helps us improve."
        if variant_key == VARIANT_ANONYMOUS:
            closing = "Thank you — your anonymous feedback has been recorded."

        flow_steps = _simulated_flow_steps(
            questions=questions,
            variant=variant_key,
            closing=closing,
            buttons=preview.get("buttons") or [],
        )

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
                    "wa_template_id": template.id,
                },
            )
        except Exception:
            script_result = {}

        wa_questions = script_result.get("whatsapp_questions")
        if isinstance(wa_questions, list) and wa_questions:
            questions = [str(q.get("text") or q) if isinstance(q, dict) else str(q) for q in wa_questions[:question_count]]

        return {
            "ok": True,
            "survey_type": {
                "id": survey_type.id,
                "slug": survey_type.slug,
                "name": survey_type.name,
            },
            "variant": variant_key,
            "length": length_key,
            "question_count": question_count,
            "anonymous_responses": variant_key == VARIANT_ANONYMOUS,
            "allow_follow_up": variant_key != VARIANT_ANONYMOUS,
            "wa_template_id": template.id,
            "wa_template_name": template.name,
            "wa_template_send_id": template.template_id,
            "template_preview": preview,
            "questions": questions,
            "flow_steps": flow_steps,
            "whatsapp_flow": {
                "intro": preview.get("rendered_body") or "",
                "questions": [{"text": q, "reply_type": "text", "options": []} for q in questions],
                "closing": closing,
            },
            "approved_script": script_result.get("script_text") or "\n".join(
                ["INTRO", preview.get("rendered_body") or "", "", "QUESTIONS"]
                + [f"{i + 1}. {q}" for i, q in enumerate(questions)]
                + ["", "CLOSING", closing]
            ),
            "system_prompt": script_result.get("system_prompt") or "",
        }

    @staticmethod
    def validate_order_config(config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if str(config.get("delivery") or "").lower() != "whatsapp" and "whatsapp" not in str(config.get("contact_method") or "").lower():
            return errors
        if not config.get("survey_type_id"):
            errors.append("Survey type is required for WhatsApp surveys")
        if not config.get("wa_template_id") and not config.get("survey_type_id"):
            errors.append("WhatsApp template is required")
        return errors
