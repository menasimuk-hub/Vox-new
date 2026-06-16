"""Build searchable menu haystack for voice interpretation."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerProfile


def build_menu_haystack(
    db: Session,
    restaurant_id: str | None,
    *,
    customer: CustomerProfile | None = None,
) -> list[dict[str, Any]]:
    if not restaurant_id:
        return []
    from app.abuu.agent.kb import get_menu

    menu = get_menu(db, restaurant_id, customer=customer)
    haystack: list[dict[str, Any]] = []
    for row in menu:
        haystack.append(
            {
                "id": row["id"],
                "name": row.get("name_ar") or row.get("name_en") or "",
                "name_ar": row.get("name_ar") or "",
                "name_en": row.get("name_en") or "",
                "category": row.get("category") or "",
                "category_ar": row.get("category") or "",
                "item_type": row.get("item_type") or "",
            }
        )
    return haystack
