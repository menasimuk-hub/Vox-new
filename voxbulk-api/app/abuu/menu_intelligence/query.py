"""Search query model for structured menu retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MenuQuery:
    categories: list[str] = field(default_factory=list)
    item_types: list[str] = field(default_factory=list)
    exclude_item_types: list[str] = field(default_factory=list)
    dietary_required: list[str] = field(default_factory=list)
    allergen_avoid: list[str] = field(default_factory=list)
    offer_only: bool = False
    drink_only: bool = False
    dessert_only: bool = False
    protein_tags: list[str] = field(default_factory=list)
    limit: int = 12

    @staticmethod
    def from_categories(categories: list[str] | None, *, limit: int = 12) -> "MenuQuery":
        cats = [str(c).strip().lower() for c in (categories or []) if str(c).strip()]
        q = MenuQuery(categories=cats, limit=limit)
        if "drinks" in cats:
            q.drink_only = True
        if "dessert" in cats:
            q.dessert_only = True
        if "offers" in cats or "offer" in cats:
            q.offer_only = True
        if "vegetarian" in cats:
            q.dietary_required.append("vegetarian")
        if "vegan" in cats:
            q.dietary_required.append("vegan")
        return q
