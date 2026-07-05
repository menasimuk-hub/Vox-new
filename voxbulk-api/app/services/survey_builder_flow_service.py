"""Strict builder survey flow — resolve steps only from frozen template-id sequence."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.models.survey_type import SurveyType
from app.services.survey_wa_vague_negative_followup_service import parse_auto_followup_from_template
from app.services.survey_step_bank_service import (
    STEP_REPLY_CONFIG,
    _body_text,
    _buttons_from_components,
    _effective_components,
    normalize_step_role,
)
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService
from app.services.survey_builder_runtime_service import (
    SurveyBuilderFlowError,
    has_builder_runtime,
    load_builder_runtime,
    runtime_step_sequence,
    sanitize_order_config_for_builder,
)

logger = logging.getLogger(__name__)
LOG_PREFIX = "[builder-flow]"


# Legacy graph/role fields must not coexist with builder-bound runtime config.
_STALE_GRAPH_KEYS = (
    "flow_snapshot",
    "flow_snapshot_json",
    "flow_definition_id",
    "flow_branches",
    "order_config_flow",
)


def is_builder_bound_flow(config: dict[str, Any]) -> bool:
    return has_builder_runtime(config)


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
    """Remove stale graph/role artifacts; prefer immutable builder_runtime when present."""
    return sanitize_order_config_for_builder(config)


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


def _shorten_question_text(text: str, *, max_len: int = 60) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[: max_len - 1].rstrip()}…"


def _normalize_label_compare(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def is_campaign_copy_label(
    candidate: str,
    *,
    campaign_title: str = "",
    campaign_goal: str = "",
) -> bool:
    """True when a label is really the survey title/goal — must not be used as a step name."""
    c = _normalize_label_compare(candidate)
    if not c:
        return False
    c_short = c[:60]
    for raw in (campaign_title, campaign_goal):
        r = _normalize_label_compare(raw)
        if not r:
            continue
        r_short = r[:60]
        if c == r or c in r or r in c:
            return True
        if c_short and (c_short == r_short or c_short in r or r_short in c or c_short in r_short):
            return True
    return False


def resolve_config_survey_type_name(
    config: dict[str, Any] | None,
    db: Session | None = None,
) -> str:
    cfg = config if isinstance(config, dict) else {}
    name = str(cfg.get("survey_type_name") or "")
    runtime = load_builder_runtime(cfg)
    if isinstance(runtime, dict) and runtime.get("survey_type_name"):
        name = str(runtime.get("survey_type_name") or name)
    if name.strip() or db is None:
        return name.strip()
    type_id = str(cfg.get("survey_type_id") or "").strip()
    if not type_id:
        selected = cfg.get("selected_survey_type_ids") or []
        if isinstance(selected, list) and selected:
            type_id = str(selected[0] or "").strip()
    if type_id:
        row = db.get(SurveyType, type_id)
        if row is not None:
            return str(row.name or "").strip()
    return ""


def resolve_step_display_name(
    question: dict[str, Any],
    *,
    sequence: int,
    survey_type_name: str = "",
    campaign_title: str = "",
    campaign_goal: str = "",
) -> str:
    """Single resolver for Step 1+ labels — never use survey title/goal as a step label."""
    for key in ("display_name", "template_name", "name"):
        name = str(question.get(key) or "").strip()
        if name and not is_campaign_copy_label(
            name, campaign_title=campaign_title, campaign_goal=campaign_goal
        ):
            return name.split(" — ")[0].strip()
    text = _shorten_question_text(str(question.get("text") or question.get("body") or ""))
    raw_text = str(question.get("text") or question.get("body") or "").strip()
    if raw_text and not is_campaign_copy_label(
        raw_text, campaign_title=campaign_title, campaign_goal=campaign_goal
    ):
        if text and not is_campaign_copy_label(text, campaign_title=campaign_title, campaign_goal=campaign_goal):
            return text
    question_label = f"Question {sequence + 1}"
    return question_label


def ensure_question_display_name(
    question: dict[str, Any],
    *,
    sequence: int,
    survey_type_name: str = "",
    campaign_title: str = "",
    campaign_goal: str = "",
) -> dict[str, Any]:
    """Fill missing display_name / template_name so Step 1+ always has a human-readable label."""
    out = dict(question)
    name = resolve_step_display_name(
        out,
        sequence=sequence,
        survey_type_name=survey_type_name,
        campaign_title=campaign_title,
        campaign_goal=campaign_goal,
    )
    out["display_name"] = name
    if not str(out.get("template_name") or "").strip():
        out["template_name"] = name
    return out


def survey_step_labels_from_config(
    config: dict[str, Any] | None,
    *,
    campaign_title: str = "",
    campaign_goal: str = "",
    db: Session | None = None,
) -> list[str]:
    """Resolved middle-step labels for list/detail APIs (includes old drafts with blank names)."""
    cfg = config if isinstance(config, dict) else {}
    goal = str(campaign_goal or cfg.get("goal") or "")
    survey_type_name = resolve_config_survey_type_name(cfg, db)
    steps = runtime_step_sequence(cfg)
    if not steps:
        raw_seq = cfg.get("builder_step_sequence") or []
        if isinstance(raw_seq, list):
            from app.services.survey_builder_runtime_service import sanitize_runtime_step_sequence

            steps = sanitize_runtime_step_sequence(
                [q for q in raw_seq if isinstance(q, dict)],
                survey_type_name=survey_type_name,
                campaign_title=campaign_title,
                campaign_goal=goal,
            )
    labels: list[str] = []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        existing = str(step.get("display_name") or "").strip()
        if existing and not is_campaign_copy_label(
            existing, campaign_title=campaign_title, campaign_goal=goal
        ):
            labels.append(existing.split(" — ")[0].strip())
            continue
        labels.append(
            resolve_step_display_name(
                step,
                sequence=idx,
                survey_type_name=survey_type_name,
                campaign_title=campaign_title,
                campaign_goal=goal,
            )
        )
    return labels


def normalize_survey_config_step_labels(
    config: dict[str, Any] | None,
    *,
    campaign_title: str = "",
) -> dict[str, Any]:
    """Sanitize step names in persisted config when loading old saved drafts / campaigns."""
    cfg = dict(config) if isinstance(config, dict) else {}
    campaign_goal = str(cfg.get("goal") or "")
    survey_type_name = str(cfg.get("survey_type_name") or "")
    runtime = load_builder_runtime(cfg)
    if isinstance(runtime, dict):
        survey_type_name = str(runtime.get("survey_type_name") or survey_type_name)
        from app.services.survey_builder_runtime_service import sanitize_runtime_step_sequence

        steps = sanitize_runtime_step_sequence(
            [q for q in (runtime.get("step_sequence") or []) if isinstance(q, dict)],
            survey_type_name=survey_type_name,
            campaign_title=campaign_title,
            campaign_goal=campaign_goal,
        )
        runtime_out = dict(runtime)
        runtime_out["step_sequence"] = steps
        cfg["builder_runtime"] = runtime_out
        cfg["builder_step_sequence"] = steps
        wa = dict(cfg.get("whatsapp_flow") or {})
        wa["questions"] = steps
        cfg["whatsapp_flow"] = wa
    elif isinstance(cfg.get("builder_step_sequence"), list):
        from app.services.survey_builder_runtime_service import sanitize_runtime_step_sequence

        cfg["builder_step_sequence"] = sanitize_runtime_step_sequence(
            [q for q in cfg["builder_step_sequence"] if isinstance(q, dict)],
            survey_type_name=survey_type_name,
            campaign_title=campaign_title,
            campaign_goal=campaign_goal,
        )
    return cfg


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
    auto_followup = parse_auto_followup_from_template(row)
    question: dict[str, Any] = {
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
    if auto_followup:
        question["auto_followup"] = auto_followup
    return question


def build_builder_step_sequence(
    db: Session,
    *,
    middle_template_ids: list[int | str],
    business_name: str = "Your business",
    first_name: str = "Alex",
    survey_type_name: str = "",
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
            ensure_question_display_name(
                question_from_template_row(
                    db,
                    row,
                    sequence=idx,
                    business_name=business_name,
                    first_name=first_name,
                ),
                sequence=idx,
                survey_type_name=survey_type_name,
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


from app.services.survey_wa_flow_constants import TELL_US_MORE_TRIGGER_ROLES

TELL_US_MORE_SOURCES = frozenset({"builder_tell_us_more_template", "builder_tell_us_more"})


def is_tell_us_more_branch_question(question: dict[str, Any] | None) -> bool:
    """True for the low-rating tell-us-more branch — never Meta HSM."""
    if not isinstance(question, dict):
        return False
    source = str(question.get("source") or "").strip()
    if source in TELL_US_MORE_SOURCES:
        return True
    node_key = str(question.get("node_key") or "")
    return node_key.startswith("builder_tell_")


def effective_tell_us_more_low_threshold(config: dict[str, Any]) -> int:
    if load_builder_runtime(config) is not None:
        from app.services.survey_builder_runtime_service import runtime_low_rating_threshold

        return runtime_low_rating_threshold(config)
    try:
        return int(config.get("tell_us_more_low_rating_threshold") or 6)
    except (TypeError, ValueError):
        return 6


def as_open_text_tell_us_more_question(question: dict[str, Any]) -> dict[str, Any]:
    """Tell-us-more is always session free-form — ignore stale BUTTONS on template rows."""
    out = dict(question)
    out["reply_type"] = "long_text"
    out["options"] = []
    return out


def question_from_tell_us_more_template(
    db: Session,
    config: dict[str, Any],
    *,
    business_name: str = "Your business",
    first_name: str = "Alex",
    order_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any] | None:
    if load_builder_runtime(config) is not None:
        from app.services.survey_builder_runtime_service import question_from_runtime_tell_us_more

        return question_from_runtime_tell_us_more(
            db,
            config,
            business_name=business_name,
            first_name=first_name,
            order_id=order_id,
            session_id=session_id,
        )
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
    return as_open_text_tell_us_more_question(q)


def is_tell_us_more_trigger_role(step_role: str) -> bool:
    return normalize_step_role(str(step_role or "")) in TELL_US_MORE_TRIGGER_ROLES


def _rating_answer_is_low(
    answer: str,
    *,
    threshold: int = 6,
    question: dict[str, Any] | None = None,
) -> bool:
    """True when numeric rating is low or button label is the worst scale option."""
    from app.services.survey_wa_flow_constants import LOW_RATING_LABELS

    raw = str(answer or "").strip()
    if not raw:
        return False
    try:
        return int(raw) < threshold + 1
    except ValueError:
        pass
    lowered = raw.lower()
    if lowered in LOW_RATING_LABELS:
        return True
    opts = question.get("options") if isinstance(question, dict) else None
    if isinstance(opts, list) and opts:
        last = str(opts[-1] or "").strip().lower()
        if lowered == last:
            return True
        first = str(opts[0] or "").strip().lower()
        if lowered == first and first in {"excellent", "great", "very helpful", "yes", "10"}:
            return False
    return False


def is_low_answer_for_tell_us_more(
    answer: str,
    *,
    threshold: int = 6,
    question: dict[str, Any] | None = None,
) -> bool:
    """Worst scale button or low numeric score — triggers tell-us-more branch."""
    if isinstance(question, dict):
        role = normalize_step_role(str(question.get("step_role") or ""))
        if role == "yes_no":
            lowered = str(answer or "").strip().lower()
            if lowered in {"no", "not really", "nah", "nope", "n"}:
                return True
    return _rating_answer_is_low(answer, threshold=threshold, question=question)


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

    runtime = load_builder_runtime(config)
    tell_us_more_active = runtime is None or bool(
        ((runtime.get("branches") or {}).get("tell_us_more_on_low_rating") or {}).get("enabled")
    )
    threshold = effective_tell_us_more_low_threshold(config)

    if (
        is_builder_bound_flow(config)
        and tell_tid
        and tell_us_more_active
        and not tell_already
        and is_tell_us_more_trigger_role(role)
        and is_low_answer_for_tell_us_more(last_answer, threshold=threshold, question=current_q)
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
    steps = runtime_step_sequence(config)
    if steps:
        return steps
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
    """1-based step index — builder flows use immutable builder_runtime.step_sequence only."""
    if load_builder_runtime(config) is not None:
        from app.services.survey_builder_runtime_service import resolve_runtime_step

        q = resolve_runtime_step(config, step, order_id=order_id, session_id=session_id)
        assert_builder_template_allowed(
            config,
            q.get("template_id"),
            context=f"resolve_conversation_step step={step}",
            order_id=order_id,
            session_id=session_id,
        )
        return q
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
