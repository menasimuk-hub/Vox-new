"""Structured menu search with type and tag filtering."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerProfile, RestaurantMenuCategory, RestaurantMenuItem
from app.abuu.menu_intelligence.query import MenuQuery
from app.abuu.menu_intelligence.query_expansion import apply_food_synonyms
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
from app.abuu.services.preference_service import category_keywords, item_types_for_categories, match_food_categories
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class MenuSearchService:
    @staticmethod
    def search(
        db: Session,
        restaurant_id: str,
        query: MenuQuery,
        *,
        customer: CustomerProfile | None = None,
    ) -> list[RestaurantMenuItem]:
        final_query = apply_food_synonyms(query.text_query or "")
        search_query = query
        if final_query or query.categories:
            merged_categories = list(query.categories or [])
            for cat in match_food_categories(final_query):
                if cat not in merged_categories:
                    merged_categories.append(cat)
            if merged_categories != list(query.categories or []) or final_query != (query.text_query or ""):
                search_query = MenuQuery(
                    categories=merged_categories,
                    item_types=list(query.item_types),
                    exclude_item_types=list(query.exclude_item_types),
                    dietary_required=list(query.dietary_required),
                    allergen_avoid=list(query.allergen_avoid),
                    offer_only=query.offer_only,
                    drink_only=query.drink_only,
                    dessert_only=query.dessert_only,
                    protein_tags=list(query.protein_tags),
                    text_query=final_query,
                    limit=query.limit,
                )

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

        allowed_legacy = set(item_types_for_categories(list(search_query.categories or [])))
        if search_query.item_types:
            allowed_legacy |= {normalize_item_type(t) for t in search_query.item_types}
            allowed_legacy |= set(search_query.item_types)

        rows = list(
            db.execute(
                select(RestaurantMenuItem)
                .where(
                    RestaurantMenuItem.category_id.in_(category_ids),
                    RestaurantMenuItem.is_deleted.is_(False),
                    RestaurantMenuItem.is_available.is_(True),
                )
                .order_by(RestaurantMenuItem.item_type.asc(), RestaurantMenuItem.created_at.asc())
                .limit(max(search_query.limit * 4, 40))
            ).scalars().all()
        )

        dislikes = parse_dislikes(customer) if customer else []
        strict = get_settings().abuu_allergen_strict_mode

        scored: list[tuple[int, RestaurantMenuItem]] = []
        for item in rows:
            if not MenuSearchService._matches_type_filter(item, search_query, allowed_legacy):
                continue
            if not MenuSearchService._matches_category_keywords(
                item,
                search_query.categories,
                text_query=final_query,
            ):
                continue
            hay = f"{item.name_en} {item.name_ar} {item.item_type}".lower()
            if any(d in hay for d in dislikes):
                continue
            safety = MenuSafetyFilter.check_item(
                item,
                allergen_avoid=search_query.allergen_avoid,
                dietary_required=search_query.dietary_required,
                strict=strict,
            )
            if not safety.allowed:
                continue
            score = MenuSearchService._score_item(item, search_query, uncertain=safety.uncertain)
            if final_query:
                fq = final_query.lower()
                item_hay = f"{item.name_en} {item.name_ar}".lower()
                if fq in item_hay or any(part in item_hay for part in fq.split() if len(part) >= 2):
                    score += 12
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        results = [item for _, item in scored[: search_query.limit]]
        logger.info(
            "abuu_menu_search | query=%r results_count=%s",
            final_query or search_query.text_query,
            len(results),
        )
        return results

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
    def _matches_category_keywords(
        item: RestaurantMenuItem,
        categories: list[str] | None,
        *,
        text_query: str = "",
    ) -> bool:
        hay = f"{item.name_en} {item.name_ar} {item.item_type}".lower()
        fq = str(text_query or "").strip().lower()
        if fq and (fq in hay or any(part in hay for part in fq.split() if len(part) >= 2)):
            return True
        if not categories:
            return not fq
        keywords = [kw.lower() for cat in categories for kw in category_keywords(cat)]
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
