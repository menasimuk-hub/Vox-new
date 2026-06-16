"""Structured trace logging for waiter pipeline."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def trace(event: str, **fields: Any) -> None:
    if not get_settings().abuu_waiter_trace_enabled:
        return
    logger.info("abuu_waiter_trace %s %s", event, fields)
