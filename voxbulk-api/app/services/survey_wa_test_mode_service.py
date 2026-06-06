"""Structured logging when Step 5 send-test runs (same engine as live, one phone only)."""

from __future__ import annotations

import logging
from typing import Any

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.services.survey_builder_runtime_service import load_builder_runtime

logger = logging.getLogger(__name__)


def is_wa_test_mode(config: dict[str, Any]) -> bool:
    return bool(config.get("wa_builder_test") or config.get("test_mode"))


def _runtime_hash(config: dict[str, Any]) -> str | None:
    runtime = load_builder_runtime(config) or {}
    raw = runtime.get("hash") or config.get("builder_runtime_hash")
    return str(raw).strip() if raw else None


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
    """Emit wa_test_mode_{phase} when config is an isolated builder test run."""
    if not is_wa_test_mode(config):
        return
    logger.info(
        "wa_test_mode_%s order_id=%s recipient_id=%s session_id=%s phone=%s "
        "current_step=%s next_template_id=%s next_template_name=%s runtime_hash=%s "
        "source=builder_runtime branch=%s extra=%s",
        phase,
        order.id,
        recipient.id,
        session.id if session else None,
        recipient.phone,
        current_step,
        next_template_id,
        next_template_name,
        _runtime_hash(config),
        branch,
        extra or {},
    )
