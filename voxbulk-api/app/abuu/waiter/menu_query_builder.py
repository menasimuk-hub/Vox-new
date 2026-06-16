"""Map intent and hints to MenuQuery."""

from __future__ import annotations

from app.abuu.conversation.intent_router import AbuuIntent
from app.abuu.menu_intelligence.query import MenuQuery
from app.abuu.waiter.interpretation import InterpretationResult


def build_menu_query(intent: AbuuIntent, interpretation: InterpretationResult | None = None) -> MenuQuery:
    categories = list(intent.categories or [])
    if interpretation:
        for hint in interpretation.category_hints:
            if hint not in categories:
                categories.append(hint)
    q = MenuQuery.from_categories(categories or None, limit=12)
    text = (interpretation.normalized_transcript if interpretation else "") or (intent.item_query or "")
    low = text.lower()
    if "cola" in low or "كولا" in low:
        q.drink_only = True
        if "drinks" not in q.categories:
            q.categories.append("drinks")
    if interpretation:
        for tok in interpretation.protected_tokens:
            if tok in {"دجاج", "chicken", "djaj"} and "chicken" not in q.protein_tags:
                q.protein_tags.append("chicken")
            if tok in {"سمك", "fish"} and "fish" not in q.protein_tags:
                q.protein_tags.append("fish")
    if intent.name == "offers":
        q.offer_only = True
    return q
