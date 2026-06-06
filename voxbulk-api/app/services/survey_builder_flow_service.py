"""Strict builder survey flow — resolve steps only from frozen template-id sequence."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_flow_compiler_service import compile_linear_graph
from app.services.survey_flow_config_service import attach_flow_to_config
from app.services.survey_flow_constants import NODE_TYPE_QUESTION
from app.services.survey_step_bank_service import (
    STEP_REPLY_CONFIG,
    _body_text,
    _buttons_from_components,
    _effective_components,
    normalize_step_role,
)
from app.services.survey_tell_us_more_flow_service import tell_us_more_flow_branches
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService

logger = logging.getLogger(__name__)
LOG_PREFIX = "[builder-flow]"


class SurveyBuilderFlowError(ValueError):
    """Next survey step cannot be resolved from the active builder sequence."""


def _options_from_template(row: TelnyxWhatsappTemplate, role: str) -> list[str]:
    components = _effective_components(row)
    buttons = _buttons_from_components(components)
    labels: list[str] = []
    for btn in buttons:
        if not isinstance(btn, dict):
            continue
        label = str(btn.get("text") or btn.get("label") or "").strip()
        if label:
            labels.append(label)
    if labels:
        return labels[:12]
    return list(STEP_REPLY_CONFIG.get(role, {}).get("options") or [])


def _reply_type_for(role: str, options: list[str]) -> str:
    cfg = STEP_REPLY_CONFIG.get(role, {})
    if options:
        return str(cfg.get("reply_type") or "choice")
    return str(cfg.get("reply_type") or "text")


def question_from_template_row(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    sequence: int,
    business_name: str = "Your business",
    first_name: str = "Alex",
) -> dict[str, Any]:
    role = normalize_step_role(row.step_role or f"step_{sequence}")
    options = _options_from_template(row, role)
    preview = SurveyWhatsappTemplateService.build_preview(
        db,
        row,
        business_name=business_name,
        first_name=first_name,
    )
    body = str(preview.get("rendered_body") or _body_text(row) or row.body_preview or "").strip()
    node_key = f"builder_step_{sequence}"
    return {
        "sequence": sequence,
        "node_key": node_key,
        "template_id": int(row.id),
        "template_name": str(row.name or ""),
        "display_name": str(row.display_name or row.name or ""),
        "step_role": role,
        "text": body,
        "reply_type": _reply_type_for(role, options),
        "options": options,
        "source": "builder_template_row",
    }


def build_builder_step_sequence(
    db: Session,
    *,
    middle_template_ids: list[int | str],
    business_name: str = "Your business",
    first_name: str = "Alex",
) -> list[dict[str, Any]]:
    """Ordered middle steps — one dict per wizard-selected template id (no step-bank role pool)."""
    steps: list[dict[str, Any]] = []
    for idx, raw_id in enumerate(middle_template_ids):
        try:
            tid = int(raw_id)
        except (TypeError, ValueError):
            continue
        if tid <= 0:
            continue
        row = db.get(TelnyxWhatsappTemplate, tid)
        if row is None or not row.active_for_survey:
            raise SurveyBuilderFlowError(f"Builder template {tid} not found or inactive.")
        steps.append(
            question_from_template_row(
                db,
                row,
                sequence=idx,
                business_name=business_name,
                first_name=first_name,
            )
        )
    if not steps:
        raise SurveyBuilderFlowError("Builder step sequence is empty — select templates in Step 3.")
    logger.info(
        "%s built sequence count=%s template_ids=%s",
        LOG_PREFIX,
        len(steps),
        [s["template_id"] for s in steps],
    )
    return steps


def build_builder_template_ids(
    *,
    welcome_template_id: int | str | None,
    middle_template_ids: list[int | str],
    thank_you_template_id: int | str | None,
    tell_us_more_template_id: int | str | None = None,
) -> list[int]:
    ordered: list[int] = []
    for raw in (welcome_template_id, *middle_template_ids, tell_us_more_template_id, thank_you_template_id):
        if raw is None:
            continue
        try:
            tid = int(raw)
        except (TypeError, ValueError):
            continue
        if tid > 0 and tid not in ordered:
            ordered.append(tid)
    return ordered


def compile_builder_sequence_graph(
    db: Session,
    *,
    step_sequence: list[dict[str, Any]],
    page_roles: list[str],
    closing_body: str,
    max_question_visits: int,
    tell_us_more_template_id: int | str | None = None,
    flow_definition_id: str | None = None,
    survey_type_id: str | None = None,
    privacy_mode: str = "off",
    page_count: int = 5,
) -> dict[str, Any]:
    """Graph snapshot whose nodes mirror builder_step_sequence order (not step-bank defaults)."""
    questions = [{**q, "step_role": q.get("node_key") or q.get("step_role")} for q in step_sequence]
    middle_roles = [str(q.get("node_key") or f"builder_step_{q.get('sequence', i)}") for i, q in enumerate(step_sequence)]

    branches = []
    has_rating = any(normalize_step_role(str(q.get("step_role") or "")) == "rating" for q in step_sequence)
    tell_node_key: str | None = None
    if tell_us_more_template_id and has_rating:
        tell_row = db.get(TelnyxWhatsappTemplate, int(tell_us_more_template_id))
        if tell_row is not None:
            tell_node_key = f"builder_tell_{int(tell_us_more_template_id)}"
            tell_q = question_from_template_row(db, tell_row, sequence=len(step_sequence))
            tell_q["node_key"] = tell_node_key
            tell_q["step_role"] = "reason"
            questions.append({**tell_q, "step_role": tell_node_key})
            middle_roles_for_compile = middle_roles + [tell_node_key]
            branches = []
            for q in step_sequence:
                if normalize_step_role(str(q.get("step_role") or "")) == "rating":
                    from_key = str(q.get("node_key") or "")
                    for br in tell_us_more_flow_branches():
                        branches.append({**br, "from_step_role": from_key, "to_step_role": tell_node_key})
                    break
            page_roles_for_compile = ["start", *middle_roles_for_compile, "completion"]
        else:
            page_roles_for_compile = ["start", *middle_roles, "completion"]
    else:
        page_roles_for_compile = ["start", *middle_roles, "completion"]

    snapshot = compile_linear_graph(
        page_roles=page_roles_for_compile,
        questions=questions,
        max_question_visits=max_question_visits,
        closing_body=closing_body,
        flow_definition_id=flow_definition_id,
        branches=branches or None,
    )
    snapshot["builder_step_sequence"] = step_sequence
    snapshot["entry_node_key"] = middle_roles[0] if middle_roles else snapshot.get("entry_node_key")
    draft_config = {
        "survey_type_id": survey_type_id,
        "privacy_mode": privacy_mode,
        "page_count": page_count,
        "page_roles": page_roles,
        "flow_branches": branches,
        "builder_step_sequence": step_sequence,
    }
    return attach_flow_to_config(draft_config, snapshot=snapshot, flow_definition_id=flow_definition_id)


def survey_questions_from_config(config: dict[str, Any]) -> list[dict[str, Any]]:
    seq = config.get("builder_step_sequence")
    if isinstance(seq, list) and seq:
        return [q for q in seq if isinstance(q, dict)]
    flow = config.get("whatsapp_flow")
    wa = flow if isinstance(flow, dict) else {}
    return [q for q in (wa.get("questions") or []) if isinstance(q, dict)]


def resolve_conversation_step(
    config: dict[str, Any],
    step: int,
    *,
    order_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """1-based step index into the frozen builder / whatsapp question list."""
    questions = survey_questions_from_config(config)
    if step < 1 or step > len(questions):
        msg = (
            f"No question for step {step} (order={order_id}, session={session_id}, "
            f"sequence_len={len(questions)}); refusing fallback."
        )
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)
    q = questions[step - 1]
    tid = q.get("template_id")
    if not tid:
        msg = (
            f"Step {step} has no template_id (order={order_id}, session={session_id}, "
            f"step_role={q.get('step_role')}); refusing fallback."
        )
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)
    logger.info(
        "%s resolve step=%s template_id=%s template_name=%s node_key=%s source=%s order=%s session=%s",
        LOG_PREFIX,
        step,
        tid,
        q.get("template_name"),
        q.get("node_key"),
        q.get("source") or "config",
        order_id,
        session_id,
    )
    return q


def log_inbound_step_context(
    *,
    order_id: str,
    session_id: str | None,
    recipient_id: str,
    step: int,
    body: str,
    survey_type_id: str | None,
) -> None:
    logger.info(
        "%s inbound order=%s session=%s recipient=%s survey_type=%s step=%s body=%r",
        LOG_PREFIX,
        order_id,
        session_id,
        recipient_id,
        survey_type_id,
        step,
        str(body or "")[:120],
    )
