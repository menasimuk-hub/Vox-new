"""Pause between outbound WhatsApp survey messages so replies feel conversational."""

from __future__ import annotations

import logging
import time

from app.core.config import get_settings

logger = logging.getLogger(__name__)

PACING_STEP = "step"
PACING_BRANCH = "branch"


def resolve_outbound_delay_seconds(pacing: str | None) -> float:
    """Return seconds to wait before sending the next WA message (0 = send immediately)."""
    if not pacing:
        return 0.0
    settings = get_settings()
    if pacing == PACING_BRANCH:
        return max(0.0, float(settings.wa_survey_branch_delay_seconds))
    if pacing == PACING_STEP:
        return max(0.0, float(settings.wa_survey_step_delay_seconds))
    return 0.0


def pause_before_outbound(
    *,
    pacing: str | None,
    order_id: str | None = None,
    recipient_id: str | None = None,
    skip: bool = False,
) -> None:
    if skip:
        return
    delay = resolve_outbound_delay_seconds(pacing)
    if delay <= 0:
        return
    logger.info(
        "survey_wa_outbound_pause order_id=%s recipient_id=%s pacing=%s delay_seconds=%s",
        order_id,
        recipient_id,
        pacing,
        delay,
    )
    time.sleep(delay)
