"""Phase 1 pre-LLM intent extraction and deterministic restaurant/menu handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.abuu.agent import kb as menu_kb
from app.abuu.agent.prefetch import prefetch_restaurant_list
from app.abuu.agent.session import Session as AgentSession
from app.abuu.agent.session_reset import order_binds_restaurant
from app.abuu.agent.skills import _format_menu_results, _get_draft_order, _refresh_cart
from app.abuu.market.registry import get_market_agent
from app.abuu.models.entities import CustomerProfile, Restaurant
from app.abuu.services.customer_memory_service import apply_saved_address_to_order
from app.abuu.services.location_service import get_default_address
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.preference_service import match_food_categories
from app.abuu.services.reply_service import localized_name
from app.abuu.services.restaurant_discovery_service import (
    RankedRestaurant,
    pick_restaurant_by_ref,
    rank_restaurants,
)
from app.core.config import get_settings

IntentAction = Literal[
    "select_restaurant_and_show_menu",
    "select_restaurant",
    "show_menu",
    "none",
]
IntentConfidence = Literal["high", "low"]

_MENU_BROWSE_MARKERS = (
    "منيو",
    "قائمة",
    "menu",
    "إيش",
    "ايش",
    "شو",
    "what",
    "show",
    "عندك",
    "عندكم",
    "تاع",
)


@dataclass(frozen=True)
class AgentIntent:
    action: IntentAction
    restaurant_ref: str | None
    menu_query: str | None
    confidence: IntentConfidence
    restaurant_id: str | None = None


def phase1_enabled() -> bool:
    return bool(get_settings().abuu_agent_phase1_orchestration)


def _pilot_ids(db: Session) -> tuple[str, ...] | None:
    if not get_settings().abuu_pilot_only:
        return None
    return get_market_agent(db).pilot_restaurant_ids


def build_ranked_restaurants(
    db: Session,
    *,
    customer_id: str,
    limit: int = 15,
) -> list[RankedRestaurant]:
    addr = get_default_address(db, customer_id)
    lat = addr.latitude if addr else None
    lng = addr.longitude if addr else None
    return rank_restaurants(
        db,
        lat=lat,
        lng=lng,
        categories=None,
        limit=limit,
        restaurant_ids=_pilot_ids(db),
    )


def freeze_turn_restaurant_snapshot(
    db: Session,
    session: AgentSession,
    *,
    customer_id: str,
) -> list[dict[str, Any]]:
    """One stable ranked list for numeric picks for the entire inbound turn."""
    ranked = build_ranked_restaurants(db, customer_id=customer_id)
    rows = [
        {"id": r.restaurant.id, "name_en": r.restaurant.name_en, "name_ar": r.restaurant.name_ar}
        for r in ranked
    ]
    session.context["turn_ranked_restaurants"] = rows
    session.context["ranked_restaurants"] = list(rows)
    return rows


def ranked_from_snapshot(db: Session, rows: list[dict[str, Any]]) -> list[RankedRestaurant]:
    ranked: list[RankedRestaurant] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rest = db.get(Restaurant, row.get("id"))
        if rest is not None:
            ranked.append(
                RankedRestaurant(
                    restaurant=rest,
                    distance_km=0.0,
                    match_score=0,
                    is_open=rest.is_available,
                )
            )
    return ranked


def find_named_restaurant_in_text(
    db: Session,
    text: str,
    ranked: list[RankedRestaurant],
) -> Restaurant | None:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return None
    best: Restaurant | None = None
    best_len = 0
    for row in ranked:
        for name in (row.restaurant.name_ar, row.restaurant.name_en):
            candidate = str(name or "").strip().lower()
            if len(candidate) < 3:
                continue
            if candidate in normalized and len(candidate) > best_len:
                best = row.restaurant
                best_len = len(candidate)
    if best is not None:
        return best
    for row in ranked:
        picked = pick_restaurant_by_ref([row], normalized)
        if picked is not None:
            return picked
    return None


def is_menu_browse_request(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return any(marker in normalized for marker in _MENU_BROWSE_MARKERS)


def extract_intent(
    db: Session,
    *,
    text: str,
    ranked: list[RankedRestaurant],
) -> AgentIntent:
    restaurant = find_named_restaurant_in_text(db, text, ranked)
    menu_browse = is_menu_browse_request(text)
    if restaurant is not None and menu_browse:
        return AgentIntent(
            action="select_restaurant_and_show_menu",
            restaurant_ref=restaurant.id,
            menu_query=None,
            confidence="high",
            restaurant_id=restaurant.id,
        )
    if restaurant is not None:
        return AgentIntent(
            action="select_restaurant",
            restaurant_ref=restaurant.id,
            menu_query=None,
            confidence="high",
            restaurant_id=restaurant.id,
        )
    if menu_browse and restaurant is None:
        return AgentIntent(
            action="show_menu",
            restaurant_ref=None,
            menu_query=text.strip(),
            confidence="low",
        )
    return AgentIntent(
        action="none",
        restaurant_ref=None,
        menu_query=None,
        confidence="low",
    )


def cart_cleared_notice(lang: str) -> str:
    if lang == "ar":
        return "تم تفريغ السلة السابقة لأنك اخترت مطعماً جديداً.\n"
    return "Your previous cart was cleared because you picked a new restaurant.\n"


def apply_restaurant_selection(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    restaurant: Restaurant,
    ranked_rows: list[dict[str, Any]],
) -> bool:
    """Bind restaurant on session/order. Returns True if switched from another bound restaurant."""
    from app.abuu.conversation.restaurant_guard import clear_switch_context, switch_restaurant_order

    order = _get_draft_order(db, session)
    switched = False
    if order is not None and order.restaurant_id != restaurant.id:
        if order_binds_restaurant(db, order, context=session.context):
            order = switch_restaurant_order(
                db,
                customer=customer,
                order=order,
                restaurant=restaurant,
            )
            switched = True
        elif order.status == "draft":
            order.restaurant_id = restaurant.id
            db.add(order)
            db.flush()
    if order is None:
        order = AbuuOrderDraftService.ensure_order(
            db,
            customer=customer,
            restaurant=restaurant,
            existing_order=None,
        )

    apply_saved_address_to_order(db, order, customer)
    session.restaurant_id = restaurant.id
    session.active_order_id = order.id
    session.context = clear_switch_context(session.context)
    session.context["restaurant_id"] = restaurant.id
    session.context["restaurant_selected"] = True
    session.context["phase1_requested_restaurant_id"] = restaurant.id
    session.context["turn_ranked_restaurants"] = ranked_rows
    session.context["ranked_restaurants"] = list(ranked_rows)
    _refresh_cart(db, session, order)
    return switched


def format_restaurant_menu(
    db: Session,
    *,
    restaurant_id: str,
    lang: str,
    customer: CustomerProfile,
    query: str | None = None,
    limit: int = 12,
) -> str:
    if query:
        items = menu_kb.search_menu(db, restaurant_id, query, lang, customer=customer)
    else:
        rows = menu_kb.get_menu(db, restaurant_id, customer=customer)
        items = rows[:limit]
    return _format_menu_results(items, lang)


def try_category_without_restaurant_reply(
    db: Session,
    session: AgentSession,
    *,
    user_text: str,
    ranked_rows: list[dict[str, Any]],
) -> str | None:
    if session.restaurant_id:
        return None
    if not match_food_categories(user_text):
        return None
    if find_named_restaurant_in_text(db, user_text, ranked_from_snapshot(db, ranked_rows)) is not None:
        return None
    lang = session.language or "ar"
    if lang == "ar":
        return "من أي مطعم بدك؟ اكتب اسم المطعم أو قول اعرض المطاعم."
    return "Which restaurant would you like? Say a restaurant name or ask to see the list."


def try_deterministic_reply(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    user_text: str,
) -> str | None:
    if not phase1_enabled():
        return None

    if not session.context.get("prefetched_restaurant_list") and not session.restaurant_id:
        prefetch_restaurant_list(db, session, customer_id=customer.id)

    ranked_rows = freeze_turn_restaurant_snapshot(db, session, customer_id=customer.id)
    ranked = ranked_from_snapshot(db, ranked_rows)
    intent = extract_intent(db, text=user_text, ranked=ranked)
    lang = session.language or "ar"

    if intent.action == "show_menu" and intent.confidence == "low" and not session.restaurant_id:
        if lang == "ar":
            return "من أي مطعم بدك تشوف المنيو؟ اكتب اسم المطعم أو قول اعرض المطاعم."
        return "Which restaurant menu should I show? Say the restaurant name or ask for the list."

    if intent.confidence != "high" or intent.action == "none":
        return try_category_without_restaurant_reply(
            db, session, user_text=user_text, ranked_rows=ranked_rows
        )

    restaurant = db.get(Restaurant, intent.restaurant_id) if intent.restaurant_id else None
    if restaurant is None:
        return None

    switched = apply_restaurant_selection(
        db,
        session,
        customer=customer,
        restaurant=restaurant,
        ranked_rows=ranked_rows,
    )
    name = localized_name(restaurant, lang)
    prefix = cart_cleared_notice(lang) if switched else ""
    if intent.action == "select_restaurant_and_show_menu":
        menu_text = format_restaurant_menu(
            db,
            restaurant_id=restaurant.id,
            lang=lang,
            customer=customer,
        )
        if lang == "ar":
            return f"{prefix}هذا منيو {name}:\n{menu_text}"
        return f"{prefix}Here is the menu for {name}:\n{menu_text}"

    if lang == "ar":
        return f"{prefix}تم اختيار {name}. ماذا تحب أن تأكل؟"
    return f"{prefix}Selected {name}. What would you like to eat?"


def user_named_target_restaurant(
    db: Session,
    *,
    user_text: str,
    ranked_rows: list[dict[str, Any]],
) -> bool:
    ranked = ranked_from_snapshot(db, ranked_rows)
    return find_named_restaurant_in_text(db, user_text, ranked) is not None


def resolve_restaurant_ref(
    db: Session,
    session: AgentSession,
    ref: str,
) -> Restaurant | None:
    rows = session.context.get("turn_ranked_restaurants") or session.context.get("ranked_restaurants") or []
    if not isinstance(rows, list):
        rows = []
    ranked = ranked_from_snapshot(db, rows)
    if not ranked:
        return None
    direct = db.get(Restaurant, ref)
    if direct is not None:
        return direct
    return pick_restaurant_by_ref(ranked, ref)
