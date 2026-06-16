"""Conservative allergen and dietary filtering."""

from __future__ import annotations

from dataclasses import dataclass

from app.abuu.models.entities import RestaurantMenuItem
from app.abuu.menu_intelligence.vocabulary import (
    ALLERGEN_TAGS,
    DIETARY_TAGS,
    parse_json_tags,
)


@dataclass
class SafetyResult:
    allowed: bool
    uncertain: bool = False
    reason: str = ""


class MenuSafetyFilter:
    @staticmethod
    def check_item(
        item: RestaurantMenuItem,
        *,
        allergen_avoid: list[str] | None = None,
        dietary_required: list[str] | None = None,
        strict: bool = True,
    ) -> SafetyResult:
        avoid = [str(a).strip().lower() for a in (allergen_avoid or []) if str(a).strip()]
        required = [str(d).strip().lower() for d in (dietary_required or []) if str(d).strip()]
        if not avoid and not required:
            return SafetyResult(allowed=True)

        item_allergens = parse_json_tags(item.allergen_tags_json, ALLERGEN_TAGS)
        item_dietary = parse_json_tags(item.dietary_tags_json, DIETARY_TAGS)

        for allergen in avoid:
            if allergen in item_allergens:
                return SafetyResult(allowed=False, reason=f"contains_{allergen}")

        for diet in required:
            if diet in item_dietary:
                continue
            if strict and not item_dietary:
                return SafetyResult(allowed=False, uncertain=True, reason=f"unconfirmed_{diet}")
            return SafetyResult(allowed=False, reason=f"missing_{diet}")

        if avoid and not item_allergens:
            return SafetyResult(allowed=True, uncertain=True, reason="allergen_data_missing")

        return SafetyResult(allowed=True)

    @staticmethod
    def filter_items(
        items: list[RestaurantMenuItem],
        *,
        allergen_avoid: list[str] | None = None,
        dietary_required: list[str] | None = None,
        strict: bool = True,
    ) -> tuple[list[RestaurantMenuItem], list[RestaurantMenuItem]]:
        """Return (safe_items, uncertain_items)."""
        safe: list[RestaurantMenuItem] = []
        uncertain: list[RestaurantMenuItem] = []
        for item in items:
            result = MenuSafetyFilter.check_item(
                item,
                allergen_avoid=allergen_avoid,
                dietary_required=dietary_required,
                strict=strict,
            )
            if result.allowed and result.uncertain:
                uncertain.append(item)
            elif result.allowed:
                safe.append(item)
        return safe, uncertain
