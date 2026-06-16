"""Load real menu/restaurant/offer facts for the conversational agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.conversation.intent_router import AbuuIntent
from app.abuu.market.registry import get_market_agent, marketplace_scope
from app.abuu.models.entities import Restaurant, RestaurantMenuItem
from app.abuu.services.offer_service import AbuuOfferService, format_offers_list
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.preference_service import match_food_categories
from app.abuu.services.reply_service import format_shekel, localized_name
from app.abuu.services.restaurant_discovery_service import RankedRestaurant, format_restaurant_list, rank_restaurants
from app.abuu.services.yallasay_wa_snapshot_service import YallasayWaSnapshotService
from app.core.config import get_settings


@dataclass
class FoodItemFact:
    menu_item_id: str
    restaurant_id: str
    name: str
    restaurant_name: str
    price_text: str
    categories: list[str] = field(default_factory=list)


@dataclass
class FactBundle:
    intent: str
    food_items: list[FoodItemFact] = field(default_factory=list)
    restaurant_list_text: str | None = None
    offers_text: str | None = None
    menu_text: str | None = None
    customer_lines: list[str] = field(default_factory=list)
    internal_index: dict[str, dict[str, str]] = field(default_factory=dict)


def _pilot_ids(db: Session) -> tuple[str, ...] | None:
    if not get_settings().abuu_pilot_only:
        return None
    return get_market_agent(db).pilot_restaurant_ids


class FactBundleLoader:
    @staticmethod
    def load(db: Session, intent: AbuuIntent, session: AgentSession, *, customer) -> FactBundle:
        lang = session.language or "ar"
        bundle = FactBundle(intent=intent.name)

        if intent.name == "food_search":
            return FactBundleLoader._food_search(db, intent, session, customer=customer, lang=lang)

        if intent.name == "restaurant_list":
            market = get_market_agent(db)
            body = YallasayWaSnapshotService.get_body(
                db, scope=marketplace_scope(market.id), kind="restaurant_list", lang=lang
            )
            if not body or "[id=" in body:
                ranked = rank_restaurants(db, lat=None, lng=None, categories=None, limit=15, restaurant_ids=_pilot_ids(db))
                body = format_restaurant_list(ranked, lang=lang, page=0, page_size=max(15, len(ranked)))
            bundle.restaurant_list_text = body
            return bundle

        if intent.name == "offers":
            offers = AbuuOfferService.list_active(db, restaurant_id=session.restaurant_id, limit=12)
            if not offers and session.restaurant_id is None:
                offers = AbuuOfferService.list_active(db, restaurant_id=None, limit=12)
            bundle.offers_text = format_offers_list(db, offers, lang=lang)
            return bundle

        if intent.name == "menu_browse":
            rid = session.restaurant_id
            if not rid:
                bundle.customer_lines.append(
                    "قولّي شو جوعان وأنا بعرضلك أطباق، أو اسأل عن المطاعم 🍽️"
                    if lang == "ar"
                    else "Tell me what you're craving, or ask for restaurants 🍽️"
                )
                return bundle
            restaurant = db.get(Restaurant, rid)
            items = AbuuOrderDraftService.list_menu_items(db, rid, limit=500, customer=customer)
            if restaurant and items:
                lines = [f"{'Menu' if lang == 'en' else 'منيو'} — {localized_name(restaurant, lang)}"]
                for item in items:
                    lines.append(f"• {localized_name(item, lang)} — {format_shekel(item.price_agorot)}")
                bundle.menu_text = "\n".join(lines)
            return bundle

        if intent.name in {"select_item", "cart_modify"} and intent.item_query:
            return FactBundleLoader._resolve_item_query(db, intent.item_query, session, customer=customer, lang=lang)

        return bundle

    @staticmethod
    def _food_search(
        db: Session,
        intent: AbuuIntent,
        session: AgentSession,
        *,
        customer,
        lang: str,
    ) -> FactBundle:
        categories = intent.categories or match_food_categories(intent.item_query or "")
        bundle = FactBundle(intent="food_search")
        pilot = _pilot_ids(db)
        restaurant_ids = list(pilot) if pilot else []
        if not restaurant_ids:
            ranked = rank_restaurants(db, lat=None, lng=None, categories=categories or None, limit=15)
            restaurant_ids = [r.restaurant.id for r in ranked]

        ctx = session.context or {}
        allergen_avoid = ctx.get("allergen_avoid") or []
        dietary_required = ctx.get("dietary_tags") or []

        facts: list[FoodItemFact] = []
        menu_limit = 500
        for rid in restaurant_ids:
            restaurant = db.get(Restaurant, rid)
            if restaurant is None or restaurant.is_deleted or not restaurant.is_available:
                continue
            items = AbuuOrderDraftService.list_menu_items(
                db,
                rid,
                categories=categories or None,
                limit=menu_limit,
                customer=customer,
                allergen_avoid=allergen_avoid if isinstance(allergen_avoid, list) else None,
                dietary_required=dietary_required if isinstance(dietary_required, list) else None,
            )
            for item in items:
                facts.append(
                    FoodItemFact(
                        menu_item_id=item.id,
                        restaurant_id=rid,
                        name=localized_name(item, lang),
                        restaurant_name=localized_name(restaurant, lang),
                        price_text=format_shekel(item.price_agorot),
                        categories=list(categories or []),
                    )
                )

        bundle.food_items = facts
        for i, f in enumerate(facts, start=1):
            key = f"k{i}"
            bundle.internal_index[key] = {"menu_item_id": f.menu_item_id, "restaurant_id": f.restaurant_id}
            bundle.customer_lines.append(f"• {f.name} — {f.price_text} ({f.restaurant_name})")
        session.context["last_food_search"] = [
            {"menu_item_id": f.menu_item_id, "restaurant_id": f.restaurant_id, "name": f.name}
            for f in facts
        ]
        return bundle

    @staticmethod
    def _resolve_item_query(
        db: Session,
        query: str,
        session: AgentSession,
        *,
        customer,
        lang: str,
    ) -> FactBundle:
        from app.abuu.voice_interpretation.fuzzy_match import best_fuzzy_match
        from app.core.config import get_settings

        bundle = FactBundle(intent="select_item")
        min_score = int(get_settings().abuu_voice_menu_fuzzy_min_score)
        candidates: list[tuple[RestaurantMenuItem, Restaurant, int]] = []

        ctx = session.context or {}
        if any(p in str(query) for p in ("نفس الشي", "نفس الطلب", "نفس الي")):
            last = ctx.get("last_added_item") or {}
            if last.get("menu_item_id"):
                item = db.get(RestaurantMenuItem, str(last["menu_item_id"]))
                rest = db.get(Restaurant, str(last.get("restaurant_id") or ""))
                if item and rest:
                    bundle.food_items = [
                        FoodItemFact(
                            menu_item_id=item.id,
                            restaurant_id=rest.id,
                            name=localized_name(item, lang),
                            restaurant_name=localized_name(rest, lang),
                            price_text=format_shekel(item.price_agorot),
                        )
                    ]
                    bundle.internal_index["pick"] = {"menu_item_id": item.id, "restaurant_id": rest.id}
                    return bundle

        search_pool = session.context.get("last_food_search") or []
        pool_rows = [
            {
                "id": entry.get("menu_item_id"),
                "name": entry.get("name") or "",
                "name_ar": entry.get("name") or "",
                "name_en": entry.get("name") or "",
                "restaurant_id": entry.get("restaurant_id"),
            }
            for entry in search_pool
        ]
        best_pool, pool_score, ranked_pool = best_fuzzy_match(query, pool_rows, language=lang, min_score=min_score)
        if best_pool and pool_score >= min_score:
            item = db.get(RestaurantMenuItem, best_pool["id"])
            rest = db.get(Restaurant, best_pool.get("restaurant_id"))
            if item and rest:
                candidates.append((item, rest, pool_score))
        elif len(ranked_pool) >= 2 and (ranked_pool[0][1] - ranked_pool[1][1]) < 8:
            for row, score in ranked_pool[:3]:
                item = db.get(RestaurantMenuItem, row["id"])
                rest = db.get(Restaurant, row.get("restaurant_id"))
                if item and rest:
                    candidates.append((item, rest, score))

        if not candidates:
            pilot = _pilot_ids(db)
            rids = list(pilot) if pilot else [r.restaurant.id for r in rank_restaurants(db, limit=15)]
            menu_rows: list[dict] = []
            row_index: dict[str, tuple[RestaurantMenuItem, Restaurant]] = {}
            for rid in rids:
                restaurant = db.get(Restaurant, rid)
                if not restaurant:
                    continue
                for item in AbuuOrderDraftService.list_menu_items(db, rid, limit=40, customer=customer):
                    menu_rows.append(
                        {
                            "id": item.id,
                            "name": item.name_ar or item.name_en or "",
                            "name_ar": item.name_ar or "",
                            "name_en": item.name_en or "",
                            "category": "",
                            "restaurant_id": rid,
                        }
                    )
                    row_index[item.id] = (item, restaurant)
            best, score, ranked = best_fuzzy_match(query, menu_rows, language=lang, min_score=min_score)
            if best and score >= min_score:
                pair = row_index.get(best["id"])
                if pair:
                    candidates.append((pair[0], pair[1], score))
            elif len(ranked) >= 2:
                for row, sc in ranked[:3]:
                    pair = row_index.get(row["id"])
                    if pair:
                        candidates.append((pair[0], pair[1], sc))

        if len(candidates) == 1:
            item, rest, _score = candidates[0]
            bundle.food_items = [
                FoodItemFact(
                    menu_item_id=item.id,
                    restaurant_id=rest.id,
                    name=localized_name(item, lang),
                    restaurant_name=localized_name(rest, lang),
                    price_text=format_shekel(item.price_agorot),
                )
            ]
            bundle.internal_index["pick"] = {"menu_item_id": item.id, "restaurant_id": rest.id}
        elif len(candidates) > 1:
            for item, rest, _score in candidates[:5]:
                bundle.food_items.append(
                    FoodItemFact(
                        menu_item_id=item.id,
                        restaurant_id=rest.id,
                        name=localized_name(item, lang),
                        restaurant_name=localized_name(rest, lang),
                        price_text=format_shekel(item.price_agorot),
                    )
                )
                bundle.customer_lines.append(
                    f"• {localized_name(item, lang)} — {format_shekel(item.price_agorot)} ({localized_name(rest, lang)})"
                )
        return bundle
