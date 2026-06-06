"""Step 5 WA send-test forensic tracing — one trace_id per run, grep-friendly logs."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.services.survey_builder_runtime_service import load_builder_runtime

logger = logging.getLogger(__name__)

TRACE_ID_CONFIG_KEY = "survey_test_trace_id"
TRACE_ID_RESULT_KEY = "survey_test_trace_id"

# Run on VPS after Step 5 send-test and after tapping Start (replace phone suffix):
SURVEY_TEST_DEBUG_SQL = """
SELECT
  o.id AS order_id,
  r.id AS recipient_id,
  r.phone,
  r.status AS recipient_status,
  r.result_json,
  s.id AS session_id,
  s.status AS session_status,
  s.current_step,
  JSON_UNQUOTE(JSON_EXTRACT(s.flow_snapshot_json, '$.awaiting_start')) AS awaiting_start,
  s.flow_mode,
  s.updated_at AS session_updated_at
FROM service_order_recipients r
JOIN service_orders o ON o.id = r.order_id
LEFT JOIN survey_sessions s ON s.recipient_id = r.id
WHERE REPLACE(REPLACE(r.phone, '+', ''), ' ', '') LIKE CONCAT('%', REPLACE(:phone_digits, '+', ''), '%')
ORDER BY s.updated_at DESC, r.updated_at DESC
LIMIT 10;
""".strip()

LOOKUP_REASONS = frozenset(
    {
        "no_recipient_for_phone",
        "recipient_found_no_session",
        "session_found_wrong_status",
        "org_mismatch",
        "phone_mismatch",
        "awaiting_start_missing",
        "builder_runtime_missing",
        "session_found_ok",
    }
)

START_MATCHERS = frozenset(
    {
        "button_title",
        "button_id",
        "plain_text_exact",
        "plain_text_fuzzy",
        "runtime_start_trigger",
        "structured_button",
    }
)


def is_wa_test_mode(config: dict[str, Any]) -> bool:
    return bool(config.get("wa_builder_test") or config.get("test_mode"))


def new_trace_id() -> str:
    return f"st-{uuid.uuid4().hex[:16]}"


def trace_id_from_config(config: dict[str, Any] | None) -> str | None:
    if not isinstance(config, dict):
        return None
    raw = config.get(TRACE_ID_CONFIG_KEY) or config.get("trace_id")
    return str(raw).strip() if raw else None


def trace_id_from_recipient(recipient: ServiceOrderRecipient | None) -> str | None:
    if recipient is None:
        return None
    try:
        payload = json.loads(recipient.result_json or "{}")
        if isinstance(payload, dict):
            raw = payload.get(TRACE_ID_RESULT_KEY) or payload.get("trace_id")
            return str(raw).strip() if raw else None
    except Exception:
        pass
    return None


def resolve_trace_id(
    *,
    config: dict[str, Any] | None = None,
    recipient: ServiceOrderRecipient | None = None,
    explicit: str | None = None,
) -> str | None:
    if explicit:
        return str(explicit).strip() or None
    tid = trace_id_from_config(config)
    if tid:
        return tid
    return trace_id_from_recipient(recipient)


def attach_trace_id_to_config(config: dict[str, Any], trace_id: str) -> dict[str, Any]:
    out = dict(config)
    out[TRACE_ID_CONFIG_KEY] = trace_id
    return out


def persist_trace_id_on_recipient(
    recipient: ServiceOrderRecipient,
    trace_id: str,
    *,
    existing_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(existing_payload or {})
    try:
        parsed = json.loads(recipient.result_json or "{}")
        if isinstance(parsed, dict):
            payload = parsed
    except Exception:
        pass
    payload[TRACE_ID_RESULT_KEY] = trace_id
    recipient.result_json = json.dumps(payload, ensure_ascii=False)
    return payload


def _runtime_hash(config: dict[str, Any] | None) -> str | None:
    if not isinstance(config, dict):
        return None
    runtime = load_builder_runtime(config) or {}
    raw = runtime.get("hash") or config.get("builder_runtime_hash")
    return str(raw).strip() if raw else None


def _should_log(*, config: dict[str, Any] | None, trace_id: str | None) -> bool:
    if trace_id:
        return True
    return is_wa_test_mode(config or {})


def log_survey_test(
    event: str,
    *,
    trace_id: str | None = None,
    order_id: str | None = None,
    recipient_id: str | None = None,
    session_id: str | None = None,
    phone: str | None = None,
    org_id: str | None = None,
    runtime_hash: str | None = None,
    current_step: int | None = None,
    handler: str,
    source: str = "builder_runtime",
    result: str | None = None,
    reason: str | None = None,
    config: dict[str, Any] | None = None,
    order: ServiceOrder | None = None,
    recipient: ServiceOrderRecipient | None = None,
    session: SurveySession | None = None,
    next_template_id: Any = None,
    next_template_name: str | None = None,
    branch: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit survey_test_{event} with shared correlation fields."""
    if order is not None:
        order_id = order_id or order.id
        org_id = org_id or order.org_id
        config = config or _order_config_safe(order)
    if recipient is not None:
        recipient_id = recipient_id or recipient.id
        phone = phone or recipient.phone
    if session is not None:
        session_id = session_id or session.id
    tid = resolve_trace_id(config=config, recipient=recipient, explicit=trace_id)
    if not _should_log(config=config, trace_id=tid):
        return
    rh = runtime_hash if runtime_hash is not None else _runtime_hash(config or {})
    logger.info(
        "survey_test_%s trace_id=%s order_id=%s recipient_id=%s session_id=%s phone=%s "
        "org_id=%s runtime_hash=%s current_step=%s handler=%s source=%s result=%s reason=%s "
        "next_template_id=%s next_template_name=%s branch=%s extra=%s",
        event,
        tid,
        order_id,
        recipient_id,
        session_id,
        phone,
        org_id,
        rh,
        current_step,
        handler,
        source,
        result,
        reason,
        next_template_id,
        next_template_name,
        branch,
        extra or {},
    )


def _order_config_safe(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def log_wa_test_mode(
    phase: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    session: SurveySession | None = None,
    current_step: int | None = None,
    next_template_id: Any = None,
    next_template_name: str | None = None,
    branch: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Backward-compatible alias — maps legacy wa_test_mode phases to survey_test events."""
    event_map = {
        "started": "trace_started",
        "session_created": "session_created",
        "welcome_sent": "welcome_sent",
        "start_transition": "start_detected",
        "step_sent": "step_sent",
        "branch_taken": "branch_taken",
        "completed": "completed",
    }
    log_survey_test(
        event_map.get(phase, phase),
        order=order,
        recipient=recipient,
        config=config,
        session=session,
        current_step=current_step,
        next_template_id=next_template_id,
        next_template_name=next_template_name,
        branch=branch,
        handler="survey_wa_test_mode_service.log_wa_test_mode",
        result="ok",
        extra=extra,
    )


def log_lookup_result(
    *,
    trace_id: str | None,
    order: ServiceOrder | None,
    recipient: ServiceOrderRecipient | None,
    session: SurveySession | None,
    config: dict[str, Any] | None,
    reason: str,
    handler: str,
    phone: str | None = None,
    org_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if reason not in LOOKUP_REASONS:
        reason = "no_recipient_for_phone"
    log_survey_test(
        "lookup_result",
        trace_id=trace_id,
        order=order,
        recipient=recipient,
        session=session,
        config=config,
        phone=phone,
        org_id=org_id,
        handler=handler,
        result="ok" if reason == "session_found_ok" else "miss",
        reason=reason,
        extra=extra,
    )


def log_inbound_normalized(
    *,
    trace_id: str | None,
    config: dict[str, Any] | None,
    order: ServiceOrder | None,
    recipient: ServiceOrderRecipient | None,
    session: SurveySession | None,
    raw_body: str,
    message_type: str,
    button_title: str,
    button_id: str,
    normalized_text: str,
    normalized_action: str | None,
    handler: str,
) -> None:
    log_survey_test(
        "inbound_normalized",
        trace_id=trace_id,
        order=order,
        recipient=recipient,
        session=session,
        config=config,
        handler=handler,
        result="ok",
        extra={
            "raw_body": raw_body[:200],
            "message_type": message_type,
            "button_title": button_title[:80],
            "button_id": button_id[:80],
            "normalized_text": normalized_text[:200],
            "normalized_action": normalized_action,
        },
    )


def log_start_detection(
    *,
    trace_id: str | None,
    config: dict[str, Any] | None,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    session: SurveySession | None,
    detected: bool,
    matcher: str | None,
    handler: str,
    reply_summary: dict[str, Any] | None = None,
) -> None:
    log_survey_test(
        "start_detected" if detected else "start_not_detected",
        trace_id=trace_id,
        order=order,
        recipient=recipient,
        session=session,
        config=config,
        handler=handler,
        result="ok" if detected else "fail",
        reason=matcher if detected else "start_not_matched",
        branch=matcher,
        extra=reply_summary or {},
    )


def log_first_question_resolution(
    *,
    trace_id: str | None,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    session: SurveySession | None,
    question: dict[str, Any],
    template_row: Any | None,
    handler: str,
    phase: str,
    failure_reason: str | None = None,
) -> None:
    runtime = load_builder_runtime(config) or {}
    selected_ids = [int(x) for x in (runtime.get("selected_template_ids") or []) if x is not None]
    tid = question.get("template_id")
    try:
        tid_int = int(tid) if tid is not None else None
    except (TypeError, ValueError):
        tid_int = None
    approved = bool(
        template_row is not None and str(getattr(template_row, "status", "") or "").upper() == "APPROVED"
    )
    in_selected = tid_int in selected_ids if tid_int is not None else False
    log_survey_test(
        phase,
        trace_id=trace_id,
        order=order,
        recipient=recipient,
        session=session,
        config=config,
        handler=handler,
        current_step=0,
        next_template_id=tid,
        next_template_name=str(question.get("template_name") or ""),
        result="ok" if failure_reason is None else "fail",
        reason=failure_reason,
        extra={
            "resolved_template_id": tid,
            "resolved_template_name": question.get("template_name"),
            "source": "builder_runtime",
            "template_row_exists": template_row is not None,
            "template_approved": approved,
            "in_selected_template_ids": in_selected,
            "selected_template_ids": selected_ids,
        },
    )
