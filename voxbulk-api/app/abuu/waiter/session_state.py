"""Unified waiter session fields (adapter over agent session)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WaiterSessionState:
    phone: str
    customer_id: str | None = None
    language: str = "ar"
    stage: str = "browsing"
    active_order_id: str | None = None
    bound_restaurant_id: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    current_intent: str | None = None
    allergen_avoid: list[str] = field(default_factory=list)
    dietary_tags: list[str] = field(default_factory=list)
    allergy_uncertain: bool = False
    context: dict[str, Any] = field(default_factory=dict)
