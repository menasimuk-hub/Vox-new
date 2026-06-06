"""Ensure API payloads are JSON-serializable before FastAPI encodes the response."""

from __future__ import annotations

import json
from typing import Any


def json_safe(value: Any) -> Any:
    """Round-trip through JSON with a string fallback for non-native types."""
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))
