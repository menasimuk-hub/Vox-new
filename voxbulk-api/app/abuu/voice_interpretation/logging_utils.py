"""Structured internal logging for voice interpretation."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def log_voice_interpretation(payload: dict[str, Any]) -> None:
    logger.info("abuu_voice_interpretation %s", payload)
