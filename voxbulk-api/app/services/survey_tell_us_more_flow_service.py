"""Tell Us More follow-up flow helpers for WA Survey generation/runtime."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_flow_compiler_service import compile_linear_graph
from app.services.survey_flow_config_service import attach_flow_to_config
from app.services.survey_step_bank_service import STEP_REPLY_CONFIG, normalize_step_role


def tell_us_more_flow_branches(*, low_threshold: int = 3) -> list[dict[str, Any]]:
    """Route low rating answers to the reason (Tell Us More) step before continuing."""
    return [
        {
            "from_step_role": "rating",
            "to_step_role": "reason",
            "priority": 5,
            "rule_key": "tell_us_more.low_rating",
            "condition": {
                "op": "lte",
                "source": "last_answer.normalized_value",
                "value": str(low_threshold),
                "cast": "int",
            },
        },
    ]


def inject_reason_step_into_composed(
    composed: dict[str, Any],
    *,
    tell_us_more_template_id: int | str,
    db: Session,
) -> dict[str, Any]:
    """Ensure reason exists in page_roles and uses the Tell Us More template."""
    roles = [normalize_step_role(r) for r in (composed.get("page_roles") or [])]
    if not roles:
        return composed

    middle = [r for r in roles if r not in {"start", "completion"}]
    tell_row = db.get(TelnyxWhatsappTemplate, int(tell_us_more_template_id))
    reason_body = str(tell_row.body_preview or "Please tell us a bit more so we can improve.") if tell_row else "Please tell us a bit more so we can improve."

    if "reason" not in middle:
        rating_idx = next((i for i, r in enumerate(middle) if r == "rating"), None)
        if rating_idx is not None and rating_idx + 1 < len(middle):
            middle[rating_idx + 1] = "reason"
        elif middle:
            middle[-1] = "reason"
        else:
            middle.append("reason")
        roles = ["start", *middle, "completion"]

    pages = []
    for role in roles:
        if role == "start":
            start_page = next((p for p in (composed.get("pages") or []) if normalize_step_role(str(p.get("step_role") or "")) == "start"), None)
            pages.append(start_page or {"step_role": "start"})
            continue
        if role == "completion":
            completion_page = next((p for p in (composed.get("pages") or []) if normalize_step_role(str(p.get("step_role") or "")) == "completion"), None)
            pages.append(completion_page or {"step_role": "completion"})
            continue
        existing = next((p for p in (composed.get("pages") or []) if normalize_step_role(str(p.get("step_role") or "")) == role), None)
        if role == "reason":
            cfg = STEP_REPLY_CONFIG.get("reason", {})
            question = {
                "step_role": "reason",
                "template_id": int(tell_us_more_template_id),
                "text": reason_body,
                "reply_type": cfg.get("reply_type", "long_text"),
                "options": list(cfg.get("options") or []),
            }
            pages.append(
                {
                    "step_role": "reason",
                    "body": reason_body,
                    "question": question,
                }
            )
        elif existing:
            pages.append(existing)
        else:
            pages.append({"step_role": role, "body": role.replace("_", " ").title()})

    middle_questions = [p["question"] for p in pages if isinstance(p, dict) and p.get("question")]
    for q in middle_questions:
        if isinstance(q, dict) and normalize_step_role(str(q.get("step_role") or "")) == "reason":
            q["template_id"] = int(tell_us_more_template_id)
            q["text"] = reason_body

    whatsapp_flow = dict(composed.get("whatsapp_flow") or {})
    whatsapp_flow["questions"] = middle_questions
    whatsapp_flow["page_roles"] = roles

    return {
        **composed,
        "page_roles": roles,
        "pages": pages,
        "whatsapp_flow": whatsapp_flow,
        "questions": [q.get("text") if isinstance(q, dict) else q for q in middle_questions],
    }


def attach_tell_us_more_graph(
    *,
    composed: dict[str, Any],
    survey_type_id: str,
    privacy_mode: str,
    page_count: int,
    closing_body: str,
    max_question_visits: int,
    flow_definition_id: str | None = None,
) -> dict[str, Any]:
    middle_questions = (composed.get("whatsapp_flow") or {}).get("questions") or []
    middle_roles = [
        normalize_step_role(r)
        for r in composed.get("page_roles") or []
        if normalize_step_role(r) not in {"start", "completion"}
    ]
    branches = tell_us_more_flow_branches() if "rating" in middle_roles and "reason" in middle_roles else []
    snapshot = compile_linear_graph(
        page_roles=composed.get("page_roles") or [],
        questions=middle_questions,
        max_question_visits=max_question_visits,
        closing_body=closing_body,
        flow_definition_id=flow_definition_id,
        branches=branches or None,
    )
    draft_config = {
        "survey_type_id": survey_type_id,
        "privacy_mode": privacy_mode,
        "page_count": page_count,
        "page_roles": composed.get("page_roles") or [],
        "flow_branches": branches,
    }
    return attach_flow_to_config(draft_config, snapshot=snapshot, flow_definition_id=flow_definition_id)
