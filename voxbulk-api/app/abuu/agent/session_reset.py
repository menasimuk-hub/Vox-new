"""Session reset and restaurant-binding helpers for the Yallasay agent."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession, clear_session
from app.abuu.agent.pending_action import clear_transactional_context
from app.abuu.models.entities import CustomerOrder, CustomerOrderItem
from app.abuu.services.intent_service import is_abuu_start_message, is_restaurant_list_message
from app.abuu.services.order_draft_service import AbuuOrderDraftService

_RESET_PATTERNS = (
    re.compile(r"(?i)\b(yallasay|yalla say|يلا\s*ساي|يلاساي|يلا)\b"),
    re.compile(r"(?i)\b(start over|new order|restart)\b"),
    re.compile(r"ابدأ من جديد"),
    re.compile(r"من جديد"),
    re.compile(r"مطعم ثاني"),
    re.compile(r"غير المطعم"),
    re.compile(r"بدي أغير المطعم"),
    re.compile(r"اعرض كل المطاعم"),
    re.compile(r"اعرض المطاعم"),
    re.compile(r"^\s*(إلغاء|الغاء|الغِ|cancel)\s*$"),
)

_OFFER_PATTERNS = (
    re.compile(r"(?i)\b(offer|offers|promo|promotion|deal|deals|discount)\b"),
    re.compile(r"عرض"),
    re.compile(r"عروض"),
    re.compile(r"خصم"),
    re.compile(r"تخفيض"),
)


def is_session_reset_message(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if is_abuu_start_message(normalized):
        return True
    if is_restaurant_list_message(normalized):
        return True
    return any(pattern.search(normalized) for pattern in _RESET_PATTERNS)


def is_offer_query(text: str) -> bool:
    normalized = str(text or "").strip()
    return bool(normalized) and any(pattern.search(normalized) for pattern in _OFFER_PATTERNS)


def order_has_items(db: Session, order: CustomerOrder | None) -> bool:
    if order is None:
        return False
    count = db.execute(
        select(CustomerOrderItem.id).where(CustomerOrderItem.order_id == order.id).limit(1)
    ).scalar_one_or_none()
    return count is not None


def order_binds_restaurant(
    db: Session,
    order: CustomerOrder | None,
    *,
    context: dict[str, Any] | None = None,
) -> bool:
    if order is None:
        return False
    if order.status in {"delivered", "cancelled"}:
        return False
    if order.status == "draft":
        if order_has_items(db, order):
            return True
        ctx = context or {}
        return bool(ctx.get("restaurant_selected"))
    if order.status in {"confirmed", "sent_to_restaurant", "preparing", "ready"}:
        return True
    return False


def cancel_empty_draft(db: Session, order: CustomerOrder | None) -> None:
    if order is None or order.status != "draft":
        return
    if order_has_items(db, order):
        return
    AbuuOrderDraftService.cancel_draft(db, order)


def hard_reset_session(db: Session, session: AgentSession) -> None:
    """Clear cart, draft, messages, and restaurant binding (yallasay fresh start)."""
    order = None
    if session.active_order_id:
        order = db.get(CustomerOrder, session.active_order_id)
    if order is not None and order.status == "draft":
        AbuuOrderDraftService.clear_draft_items(db, order)
        AbuuOrderDraftService.cancel_draft(db, order)
    session.active_order_id = None
    session.cart = []
    session.stage = "browsing"
    session.restaurant_id = None
    session.messages = []
    for key in (
        "restaurant_id",
        "restaurant_selected",
        "ranked_restaurants",
        "prefetched_restaurant_list",
        "prefetched_offers",
        "prefetched_menu",
        "menu_item_index",
        "matched_offer_id",
        "matched_offer_hint",
        "offer_restaurant_switch_hint",
        "confirmed_cart_fingerprint",
        "last_food_search",
        "voice_interpretation",
        "awaiting_dish_pick",
    ):
        session.context.pop(key, None)
    clear_transactional_context(session)
    clear_session(db, session.customer_wa_number)


def clear_restaurant_binding(db: Session, session: AgentSession, *, full_reset: bool = False) -> None:
    order = None
    if session.active_order_id:
        order = db.get(CustomerOrder, session.active_order_id)
    cancel_empty_draft(db, order)
    session.restaurant_id = None
    session.context.pop("restaurant_id", None)
    session.context.pop("restaurant_selected", None)
    session.context.pop("ranked_restaurants", None)
    session.context.pop("prefetched_restaurant_list", None)
    session.context.pop("prefetched_offers", None)
    if order is not None and order.status == "draft" and not order_has_items(db, order):
        session.active_order_id = None
    if full_reset:
        session.cart = []
        session.messages = []
        session.stage = "browsing"
        clear_session(db, session.customer_wa_number)
    clear_transactional_context(session)
