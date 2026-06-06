"""Strict builder survey flow — resolve steps only from frozen template-id sequence."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_step_bank_service import (
    STEP_REPLY_CONFIG,
    _body_text,
    _buttons_from_components,
    _effective_components,
    normalize_step_role,
)
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService

logger = logging.getLogger(__name__)
LOG_PREFIX = "[builder-flow]"


class SurveyBuilderFlowError(ValueError):
    """Next survey step cannot be resolved from the active builder sequence."""


# Legacy graph/role fields must not coexist with builder-bound runtime config.
_STALE_GRAPH_KEYS = (
    "flow_snapshot",
    "flow_snapshot_json",
    "flow_definition_id",
    "flow_branches",
    "order_config_flow",
)


def is_builder_bound_flow(config: dict[str, Any]) -> bool:
    seq = config.get("builder_step_sequence")
    ids = config.get("builder_template_ids")
    return (
        isinstance(seq, list)
        and len(seq) > 0
        and isinstance(ids, list)
        and len(ids) > 0
    )


def assert_builder_template_allowed(
    config: dict[str, Any],
    template_id: Any,
    *,
    context: str,
    order_id: str | None = None,
    session_id: str | None = None,
) -> int:
    """Hard fail if runtime tries to send a template outside the wizard selection."""
    if not is_builder_bound_flow(config):
        try:
            return int(template_id)
        except (TypeError, ValueError):
            raise SurveyBuilderFlowError(f"Invalid template_id in {context}") from None
    allow = {int(x) for x in config.get("builder_template_ids") or []}
    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        msg = f"builder flow violation: missing template_id in {context} order={order_id}"
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)
    if tid not in allow:
        msg = (
            f"builder flow violation: attempted template {tid} not in selected builder_template_ids "
            f"{sorted(allow)} context={context} order={order_id} session={session_id}"
        )
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)
    return tid


def sanitize_builder_config(config: dict[str, Any]) -> dict[str, Any]:
    """Remove stale graph/role artifacts so runtime cannot read old snapshots."""
    out = dict(config)
    if not is_builder_bound_flow(out):
        return out
    for key in _STALE_GRAPH_KEYS:
        out.pop(key, None)
    out["flow_engine"] = "linear"
    seq = [q for q in (out.get("builder_step_sequence") or []) if isinstance(q, dict)]
    out["builder_step_sequence"] = seq
    wa = dict(out.get("whatsapp_flow") or {})
    wa["questions"] = seq
    out["whatsapp_flow"] = wa
    logger.info(
        "%s sanitized builder config template_ids=%s step_count=%s",
        LOG_PREFIX,
        out.get("builder_template_ids"),
        len(seq),
    )
    return out


def log_builder_step_resolution(
    *,
    phase: str,
    order_id: str | None,
    session_id: str | None,
    config: dict[str, Any],
    current_step: int | None = None,
    next_step: int | None = None,
    current_question: dict[str, Any] | None = None,
    next_question: dict[str, Any] | None = None,
    payload_source: str,
) -> None:
    def _summarize(q: dict[str, Any] | None) -> dict[str, Any]:
        if not q:
            return {}
        return {
            "template_id": q.get("template_id"),
            "template_name": q.get("template_name"),
            "node_key": q.get("node_key"),
            "step_role": q.get("step_role"),
            "text_preview": str(q.get("text") or "")[:120],
            "source": q.get("source"),
        }

    logger.info(
        "%s %s order=%s session=%s current_step=%s next_step=%s payload_source=%s "
        "builder_template_ids=%s builder_step_sequence_ids=%s current=%s next=%s",
        LOG_PREFIX,
        phase,
        order_id,
        session_id,
        current_step,
        next_step,
        payload_source,
        config.get("builder_template_ids"),
        [q.get("template_id") for q in survey_questions_from_config(config)],
        _summarize(current_question),
        _summarize(next_question),
    )


def _options_from_template(row: TelnyxWhatsappTemplate, role: str, *, strict: bool = False) -> list[str]:
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
    if strict:
        return []
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
    options = _options_from_template(row, role, strict=True)
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


def builder_generation_config(
    *,
    builder_step_sequence: list[dict[str, Any]],
    builder_template_ids: list[int],
) -> dict[str, Any]:
    """Persist only builder-linear fields — no graph snapshot that can override runtime."""
    seq = [q for q in builder_step_sequence if isinstance(q, dict)]
    wa = {"questions": seq}
    return sanitize_builder_config(
        {
            "flow_engine": "linear",
            "builder_step_sequence": seq,
            "builder_template_ids": builder_template_ids,
            "whatsapp_flow": wa,
        }
    )


def effective_order_config(config: dict[str, Any]) -> dict[str, Any]:
    """Runtime view of order config — strips stale graph when builder sequence is present."""
    if not isinstance(config, dict):
        return {}
    return sanitize_builder_config(dict(config))


def should_use_builder_linear_runtime(config: dict[str, Any]) -> bool:
    return is_builder_bound_flow(effective_order_config(config))


def question_from_tell_us_more_template(
    db: Session,
    config: dict[str, Any],
    *,
    business_name: str = "Your business",
    first_name: str = "Alex",
) -> dict[str, Any] | None:
    raw = config.get("tell_us_more_template_id")
    if not raw:
        return None
    tid = assert_builder_template_allowed(
        config,
        raw,
        context="tell_us_more_template",
    )
    row = db.get(TelnyxWhatsappTemplate, tid)
    if row is None or not row.active_for_survey:
        raise SurveyBuilderFlowError(f"Tell-us-more template {tid} not found or inactive.")
    q = question_from_template_row(
        db,
        row,
        sequence=-1,
        business_name=business_name,
        first_name=first_name,
    )
    q["node_key"] = f"builder_tell_{tid}"
    q["step_role"] = "reason"
    q["source"] = "builder_tell_us_more_template"
    return q


def _rating_answer_is_low(answer: str, *, threshold: int = 6) -> bool:
    """True when numeric rating is below threshold (default: below 7)."""
    raw = str(answer or "").strip()
    if not raw:
        return False
    try:
        return int(raw) < threshold + 1
    except ValueError:
        return False


def resolve_next_conversation_step(
    db: Session,
    config: dict[str, Any],
    *,
    current_step: int,
    answers: list[dict[str, Any]] | None = None,
    conv: dict[str, Any] | None = None,
    order_id: str | None = None,
    session_id: str | None = None,
    business_name: str = "Your business",
    first_name: str = "Alex",
) -> tuple[int, dict[str, Any], str]:
    """
    Resolve the next 1-based step index and question dict.
    Returns (next_step_index, question, payload_source).
    """
    questions = survey_questions_from_config(config)
    conv = conv or {}
    answers = answers or []

    if current_step < 1 or current_step > len(questions):
        raise SurveyBuilderFlowError(f"Invalid current_step {current_step}")

    current_q = resolve_conversation_step(
        config,
        current_step,
        order_id=order_id,
        session_id=session_id,
    )
    next_linear = current_step + 1

    payload_source = "builder_step_sequence"
    tell_tid = config.get("tell_us_more_template_id")
    tell_already = bool(conv.get("tell_us_more_asked"))
    role = normalize_step_role(str(current_q.get("step_role") or ""))
    last_answer = str(answers[-1].get("answer") or "") if answers else ""

    if (
        is_builder_bound_flow(config)
        and tell_tid
        and not tell_already
        and role == "rating"
        and _rating_answer_is_low(last_answer)
    ):
        tell_q = question_from_tell_us_more_template(
            db,
            config,
            business_name=business_name,
            first_name=first_name,
        )
        if tell_q is not None:
            log_builder_step_resolution(
                phase="resolve_next_tell_us_more",
                order_id=order_id,
                session_id=session_id,
                config=config,
                current_step=current_step,
                next_step=current_step,
                current_question=current_q,
                next_question=tell_q,
                payload_source="builder_tell_us_more_template",
            )
            return current_step, tell_q, "builder_tell_us_more_template"

    if next_linear > len(questions):
        raise SurveyBuilderFlowError(f"No next step after {current_step}")

    next_q = resolve_conversation_step(
        config,
        next_linear,
        order_id=order_id,
        session_id=session_id,
    )
    log_builder_step_resolution(
        phase="resolve_next_linear",
        order_id=order_id,
        session_id=session_id,
        config=config,
        current_step=current_step,
        next_step=next_linear,
        current_question=current_q,
        next_question=next_q,
        payload_source=payload_source,
    )
    return next_linear, next_q, payload_source


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
    if not is_builder_bound_flow(config):
        return q
    tid = q.get("template_id")
    if not tid:
        msg = (
            f"Step {step} has no template_id (order={order_id}, session={session_id}, "
            f"step_role={q.get('step_role')}); refusing fallback."
        )
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)
    assert_builder_template_allowed(
        config,
        tid,
        context=f"resolve_conversation_step step={step}",
        order_id=order_id,
        session_id=session_id,
    )
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
