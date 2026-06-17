"""Transactional pending actions — cart confirmation before generic browse routing."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.models.entities import CustomerOrder, CustomerProfile, Restaurant, RestaurantMenuItem
from app.abuu.services.customer_memory_service import apply_saved_address_to_order
from app.abuu.services.intent_service import is_restaurant_list_message
from app.abuu.services.kb_service import resolve_settings
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import format_shekel, localized_name
from app.abuu.voice_interpretation.normalize import normalize_query

ActiveFlow = Literal["browsing", "ordering", "cart_confirmation", "checkout"]

PENDING_TTL_MINUTES = 15

TRANSACTIONAL_CONTEXT_KEYS = (
    "active_flow",
    "pending_action",
    "last_presented_items",
    "last_confirmation_question",
    "bound_restaurant_id",
)

_AFFIRMATIVE_PATTERNS = (
    re.compile(r"^\s*(yes|ok|okay|yep|yeah|sure|add them|add it)\s*$", re.I),
    re.compile(r"^\s*(نعم|تمام|اوكي|أوكي|يلا|يلّا|موافق|أكيد|اكيد)\s*$"),
    re.compile(r"ضيفهم"),
    re.compile(r"أضيفهم"),
    re.compile(r"اضيفهم"),
    re.compile(r"على السلة"),
    re.compile(r"^add\s*$", re.I),
)

_NEGATIVE_PATTERNS = (
    re.compile(r"^\s*(no|nope|cancel|stop)\s*$", re.I),
    re.compile(r"^\s*(لا|لأ|لا شكرا|لا شكراً|الغ|إلغ|الغاء|إلغاء)\s*$"),
)

_CART_INQUIRY_PATTERNS = (
    re.compile(r"السلة"),
    re.compile(r"سلة"),
    re.compile(r"cart", re.I),
    re.compile(r"شو عندي"),
    re.compile(r"ايش عندي"),
    re.compile(r"إيش عندي"),
    re.compile(r"شو في"),
    re.compile(r"ايش في"),
    re.compile(r"كم صار"),
    re.compile(r"كم المجموع"),
    re.compile(r"what.*cart", re.I),
)

_EXPLICIT_EXIT_PATTERNS = (
    re.compile(r"غيّر المطعم"),
    re.compile(r"غير المطعم"),
    re.compile(r"بدي أغير"),
    re.compile(r"بدي من مطعم"),
    re.compile(r"مطعم ثاني"),
    re.compile(r"امسح السلة"),
    re.compile(r"مسح السلة"),
    re.compile(r"ابدأ من جديد"),
    re.compile(r"من جديد"),
)


def _normalized(text: str) -> str:
    return normalize_query(str(text or ""), "ar")


def is_affirmative_reply(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized:
        return False
    return any(p.search(normalized) for p in _AFFIRMATIVE_PATTERNS)


def is_negative_reply(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized:
        return False
    return any(p.search(normalized) for p in _NEGATIVE_PATTERNS)


def is_cart_inquiry(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized:
        return False
    return any(p.search(normalized) for p in _CART_INQUIRY_PATTERNS)


def is_explicit_flow_exit(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if is_restaurant_list_message(normalized):
        return True
    norm = _normalized(normalized)
    return any(p.search(norm) for p in _EXPLICIT_EXIT_PATTERNS)


def clear_transactional_context(session: AgentSession) -> None:
    session.context.pop("pending_action", None)
    session.context.pop("last_presented_items", None)
    session.context.pop("last_confirmation_question", None)
    session.context.pop("bound_restaurant_id", None)
    session.context["active_flow"] = "browsing"


def get_pending_action(session: AgentSession) -> dict[str, Any] | None:
    raw = session.context.get("pending_action")
    if not isinstance(raw, dict):
        return None
    expires = str(raw.get("expires_at") or "").strip()
    if expires:
        try:
            if datetime.fromisoformat(expires) < datetime.utcnow():
                clear_transactional_context(session)
                return None
        except ValueError:
            pass
    if str(raw.get("type") or "") != "add_items_to_cart":
        return None
    if not raw.get("restaurant_id") or not raw.get("items"):
        return None
    return raw


def is_transactional_flow(session: AgentSession) -> bool:
    flow = str(session.context.get("active_flow") or "").strip()
    if flow in {"ordering", "cart_confirmation", "checkout"}:
        return True
    if get_pending_action(session) is not None:
        return True
    if session.cart:
        return True
    if session.active_order_id:
        return True
    if session.context.get("bound_restaurant_id"):
        return True
    return False


def resolve_binding_restaurant_id(session: AgentSession, context: dict[str, Any] | None = None) -> str | None:
    ctx = context if context is not None else session.context
    pending = ctx.get("pending_action")
    if isinstance(pending, dict):
        rid = str(pending.get("restaurant_id") or "").strip()
        if rid:
            return rid
    bound = str(ctx.get("bound_restaurant_id") or "").strip()
    if bound:
        return bound
    last = ctx.get("last_added_item")
    if isinstance(last, dict):
        rid = str(last.get("restaurant_id") or "").strip()
        if rid:
            return rid
    rid = str(ctx.get("restaurant_id") or "").strip()
    return rid or None


def set_pending_add_items(
    session: AgentSession,
    *,
    restaurant_id: str,
    items: list[dict[str, Any]],
    total_agorot: int,
    delivery_fee_agorot: int = 0,
    source_message_id: str | None = None,
    confirmation_question: str | None = None,
) -> None:
    expires = (datetime.utcnow() + timedelta(minutes=PENDING_TTL_MINUTES)).isoformat(timespec="seconds")
    session.context["pending_action"] = {
        "type": "add_items_to_cart",
        "restaurant_id": restaurant_id,
        "items": items,
        "total_agorot": int(total_agorot),
        "delivery_fee_agorot": int(delivery_fee_agorot),
        "expires_at": expires,
        "source_message_id": source_message_id,
    }
    session.context["last_presented_items"] = list(items)
    session.context["bound_restaurant_id"] = restaurant_id
    session.context["restaurant_id"] = restaurant_id
    session.context["restaurant_selected"] = True
    session.context["active_flow"] = "cart_confirmation"
    if confirmation_question:
        session.context["last_confirmation_question"] = confirmation_question


def _bind_restaurant(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    restaurant: Restaurant,
) -> CustomerOrder:
    from app.abuu.agent.intent_gate import apply_restaurant_selection

    apply_restaurant_selection(
        db,
        session,
        customer=customer,
        restaurant=restaurant,
        ranked_rows=session.context.get("turn_ranked_restaurants")
        or session.context.get("ranked_restaurants")
        or [],
    )
    session.context["bound_restaurant_id"] = restaurant.id
    order = _get_draft_order(db, session)
    if order is None:
        order = AbuuOrderDraftService.ensure_order(
            db,
            customer=customer,
            restaurant=restaurant,
            existing_order=None,
        )
        apply_saved_address_to_order(db, order, customer)
        session.active_order_id = order.id
    return order


def _get_draft_order(db: Session, session: AgentSession) -> CustomerOrder | None:
    if not session.active_order_id:
        return None
    order = db.get(CustomerOrder, session.active_order_id)
    if order is None or order.status != "draft":
        return None
    return order


def _refresh_cart(db: Session, session: AgentSession, order: CustomerOrder | None) -> None:
    from app.abuu.agent.session import _cart_from_order

    session.cart = _cart_from_order(db, order)


def apply_pending_add_items(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
) -> str:
    pending = get_pending_action(session)
    if pending is None:
        raise ValueError("No pending cart action")

    restaurant_id = str(pending["restaurant_id"])
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        clear_transactional_context(session)
        raise ValueError("Restaurant not found for pending items")

    order = _bind_restaurant(db, session, customer=customer, restaurant=restaurant)
    lang = session.language or "ar"

    for row in pending.get("items") or []:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("menu_item_id") or "").strip()
        qty = max(1, int(row.get("quantity") or 1))
        item = db.get(RestaurantMenuItem, item_id)
        if item is None:
            continue
        AbuuOrderDraftService.add_item(db, order, item, quantity=qty)

    fingerprint = AbuuOrderDraftService.cart_fingerprint(db, order)
    session.context = AbuuOrderDraftService.mark_cart_changed(session.context, fingerprint)
    _refresh_cart(db, session, order)
    clear_transactional_context(session)
    session.context["active_flow"] = "ordering"
    session.context["last_added_item"] = {
        "restaurant_id": restaurant_id,
        "menu_item_id": str((pending.get("items") or [{}])[0].get("menu_item_id") or ""),
        "name": str((pending.get("items") or [{}])[0].get("name_ar") or ""),
    }

    summary = format_cart_summary_for_session(db, session, lang)
    if lang == "ar":
        return f"تمام! أضفتهم للسلة ✅\n{summary}"
    return f"Done — added to your cart ✅\n{summary}"


def format_cart_summary_for_session(db: Session, session: AgentSession, lang: str) -> str:
    order = _get_draft_order(db, session)
    if order is not None and session.cart:
        lines: list[str] = []
        for row in session.cart:
            price = format_shekel(int(row.get("price", 0) * 100))
            lines.append(f"- {row['name']} x{row['quantity']} ({price})")
        total = format_shekel(int(order.total_agorot or 0))
        if lang == "ar":
            return "السلة:\n" + "\n".join(lines) + f"\nالمجموع: {total}"
        return "Cart:\n" + "\n".join(lines) + f"\nTotal: {total}"

    pending = get_pending_action(session)
    if pending is not None:
        items = pending.get("items") or []
        lines: list[str] = []
        for row in items:
            if not isinstance(row, dict):
                continue
            name = row.get("name_ar") if lang == "ar" else row.get("name_en")
            name = name or row.get("name_ar") or row.get("name_en") or "?"
            price = format_shekel(int(row.get("price_agorot") or 0))
            qty = int(row.get("quantity") or 1)
            lines.append(f"- {name} x{qty} ({price})")
        total = format_shekel(int(pending.get("total_agorot") or 0))
        delivery = int(pending.get("delivery_fee_agorot") or 0)
        if lang == "ar":
            header = "عندك مقترح (لسا ما انضاف للسلة):\n" if pending else "السلة:\n"
            body = "\n".join(lines) + f"\nالمجموع: {total}"
            if delivery:
                body += f" + توصيل {format_shekel(delivery)}"
            return header + body
        header = "Proposed (not yet in cart):\n"
        return header + "\n".join(lines) + f"\nSubtotal: {total}"

    if lang == "ar":
        return "السلة فاضية."
    return "Cart is empty."


def confirmation_prompt(lang: str) -> str:
    if lang == "ar":
        return "أضيفهم عالسلة؟ 🙌"
    return "Shall I add them to your cart? 🙌"


def build_proposal_lines(
    db: Session,
    *,
    restaurant_id: str,
    items: list[dict[str, Any]],
    lang: str,
) -> tuple[list[dict[str, Any]], int, int]:
    """Validate and enrich item rows; returns (stored_items, total_agorot, delivery_fee_agorot)."""
    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise ValueError("Restaurant not found")

    stored: list[dict[str, Any]] = []
    total = 0
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("menu_item_id") or raw.get("item_id") or "").strip()
        qty = max(1, int(raw.get("quantity") or 1))
        item = db.get(RestaurantMenuItem, item_id)
        if item is None:
            raise ValueError(f"Item not found: {item_id}")
        stored.append(
            {
                "menu_item_id": item.id,
                "quantity": qty,
                "name_en": item.name_en,
                "name_ar": item.name_ar,
                "price_agorot": int(item.price_agorot or 0),
            }
        )
        total += int(item.price_agorot or 0) * qty

    if not stored:
        raise ValueError("No valid items to propose")

    settings = resolve_settings(db, restaurant_id=restaurant_id)
    delivery_fee = int(settings.delivery_fee_agorot or 0)
    return stored, total, delivery_fee


def format_proposal_message(
    db: Session,
    *,
    restaurant_id: str,
    items: list[dict[str, Any]],
    lang: str,
) -> str:
    stored, total, delivery_fee = build_proposal_lines(db, restaurant_id=restaurant_id, items=items, lang=lang)
    restaurant = db.get(Restaurant, restaurant_id)
    name = localized_name(restaurant, lang) if restaurant else restaurant_id
    lines: list[str] = []
    if lang == "ar":
        lines.append(f"تمام! بدي أضيفلك من {name}:")
    else:
        lines.append(f"From {name}, I can add:")
    for idx, row in enumerate(stored, start=1):
        item_name = row["name_ar"] if lang == "ar" else row["name_en"]
        item_name = item_name or row["name_en"] or row["name_ar"]
        price = format_shekel(int(row["price_agorot"]))
        lines.append(f"{idx}. *{item_name}* — {price}")
    subtotal = format_shekel(total)
    if lang == "ar":
        lines.append(f"\nالمجموع: *{subtotal}*" + (f" + توصيل {format_shekel(delivery_fee)}" if delivery_fee else ""))
        lines.append(f"\n{confirmation_prompt(lang)}")
    else:
        lines.append(f"\nSubtotal: *{subtotal}*" + (f" + delivery {format_shekel(delivery_fee)}" if delivery_fee else ""))
        lines.append(f"\n{confirmation_prompt(lang)}")
    return "\n".join(lines)
