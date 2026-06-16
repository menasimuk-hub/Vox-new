"""Structured menu search with type and tag filtering."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerProfile, RestaurantMenuCategory, RestaurantMenuItem
from app.abuu.menu_intelligence.query import MenuQuery
from app.abuu.menu_intelligence.safety_filter import MenuSafetyFilter
from app.abuu.menu_intelligence.vocabulary import (
    PROTEIN_TAGS,
    item_is_dessert,
    item_is_drink,
    item_is_offer,
    normalize_item_type,
    parse_json_tags,
)
from app.abuu.services.customer_memory_service import parse_dislikes
from app.abuu.services.preference_service import category_keywords, item_types_for_categories
from app.core.config import get_settings


class MenuSearchService:
    @staticmethod
    def search(
        db: Session,
        restaurant_id: str,
        query: MenuQuery,
        *,
        customer: CustomerProfile | None = None,
    ) -> list[RestaurantMenuItem]:
        category_ids = [
            c.id
            for c in db.execute(
                select(RestaurantMenuCategory).where(
                    RestaurantMenuCategory.restaurant_id == restaurant_id,
                    RestaurantMenuCategory.is_deleted.is_(False),
                    RestaurantMenuCategory.is_available.is_(True),
                )
            ).scalars().all()
        ]
        if not category_ids:
            return []

        allowed_legacy = set(item_types_for_categories(list(query.categories or [])))
        if query.item_types:
            allowed_legacy |= {normalize_item_type(t) for t in query.item_types}
            allowed_legacy |= set(query.item_types)

        rows = list(
            db.execute(
                select(RestaurantMenuItem)
                .where(
                    RestaurantMenuItem.category_id.in_(category_ids),
                    RestaurantMenuItem.is_deleted.is_(False),
                    RestaurantMenuItem.is_available.is_(True),
                )
                .order_by(RestaurantMenuItem.item_type.asc(), RestaurantMenuItem.created_at.asc())
                .limit(max(query.limit * 4, 40))
            ).scalars().all()
        )

        dislikes = parse_dislikes(customer) if customer else []
        strict = get_settings().abuu_allergen_strict_mode

        scored: list[tuple[int, RestaurantMenuItem]] = []
        for item in rows:
            if not MenuSearchService._matches_type_filter(item, query, allowed_legacy):
                continue
            if not MenuSearchService._matches_category_keywords(item, query.categories):
                continue
            hay = f"{item.name_en} {item.name_ar} {item.item_type}".lower()
            if any(d in hay for d in dislikes):
                continue
            safety = MenuSafetyFilter.check_item(
                item,
                allergen_avoid=query.allergen_avoid,
                dietary_required=query.dietary_required,
                strict=strict,
            )
            if not safety.allowed:
                continue
            score = MenuSearchService._score_item(item, query, uncertain=safety.uncertain)
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[: query.limit]]

    @staticmethod
    def _matches_type_filter(
        item: RestaurantMenuItem,
        query: MenuQuery,
        allowed_legacy: set[str],
    ) -> bool:
        itype = str(item.item_type or "")
        norm = normalize_item_type(itype)

        if query.drink_only:
            return item_is_drink(itype)
        if query.dessert_only:
            return item_is_dessert(itype) or "sweet" in parse_json_tags(item.recipe_tags_json, frozenset({"sweet"}))
        if query.offer_only:
            return item_is_offer(itype, item.offer_type)

        if query.exclude_item_types:
            if norm in query.exclude_item_types or itype in query.exclude_item_types:
                return False

        # Default food browse: exclude drinks, sides, offers unless category asked
        if not query.drink_only and not query.dessert_only and not query.offer_only:
            if item_is_drink(itype) and "drinks" not in (query.categories or []):
                return False
            if item_is_dessert(itype) and "dessert" not in (query.categories or []):
                return False
            if item_is_offer(itype, item.offer_type) and "offers" not in (query.categories or []):
                return False
            if itype in {"addon", "side", "sides", "sauce"} and not query.categories:
                return False

        if query.categories and allowed_legacy:
            return itype in allowed_legacy or norm in allowed_legacy
        return True

    @staticmethod
    def _matches_category_keywords(item: RestaurantMenuItem, categories: list[str] | None) -> bool:
        if not categories:
            return True
        keywords = [kw.lower() for cat in categories for kw in category_keywords(cat)]
        hay = f"{item.name_en} {item.name_ar} {item.item_type}".lower()
        if any(kw in hay for kw in keywords):
            return True
        allowed = item_types_for_categories(categories)
        return str(item.item_type or "") in allowed

    @staticmethod
    def _score_item(item: RestaurantMenuItem, query: MenuQuery, *, uncertain: bool) -> int:
        score = 10
        if str(item.classification_status or "") == "classified":
            score += 20
        elif str(item.classification_status or "") == "unclassified":
            score -= 15
        if uncertain:
            score -= 8
        proteins = parse_json_tags(item.protein_tags_json, PROTEIN_TAGS)
        for want in query.protein_tags:
            if want in proteins:
                score += 5
        for cat in query.categories:
            if cat == "fish" and "fish" in proteins:
                score += 8
            if cat == "chicken" and "chicken" in proteins:
                score += 8
        if query.drink_only and item_is_drink(item.item_type):
            score += 10
        if query.dessert_only and item_is_dessert(item.item_type):
            score += 10
        return score
