"""Transactional pending actions — cart confirmation before generic browse routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
    re.compile(r"\bسلة\b"),
    re.compile(r"cart", re.I),
    re.compile(r"basket", re.I),
    re.compile(r"شو عندي"),
    re.compile(r"ايش عندي"),
    re.compile(r"إيش عندي"),
    re.compile(r"كم صار"),
    re.compile(r"كم المجموع"),
    re.compile(r"what.*cart", re.I),
    re.compile(r"what.*basket", re.I),
    re.compile(r"show.*cart", re.I),
    re.compile(r"show.*basket", re.I),
    re.compile(r"my basket", re.I),
    re.compile(r"my order", re.I),
    re.compile(r"(ايش|شو|إيش)\s+في\s+(ال)?سلة"),
    re.compile(r"عرض.*السلة"),
    re.compile(r"شو.*السلة"),
)

_EXPLICIT_CART_NOUN = re.compile(
    r"السلة|\bسلة\b|cart|basket|عندي|المجموع|الطلب|my order",
    re.I,
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


def has_explicit_cart_noun(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized:
        return False
    return bool(
        re.search(r"السلة|\bسلة\b|cart|عندي|المجموع|الطلب", normalized, re.I)
    )


def is_cart_inquiry(text: str, *, menu_browse: bool = False) -> bool:
    normalized = _normalized(text)
    if not normalized:
        return False
    if _EXPLICIT_CART_NOUN.search(normalized):
        return True
    if menu_browse:
        return False
    if re.search(r"منيو|قائمة|menu", normalized, re.I):
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


def pending_edit_hint(lang: str) -> str:
    if lang == "ar":
        return (
            "عدّل الكمية (مثلاً: بدي 3)، أضف أرقام (1 2 3)، "
            "أو قول ضيفهم / تمام، أو اسأل عن السلة."
        )
    return "Edit qty (e.g. want 3), add numbers (1 2 3), say yes to confirm, or ask about your cart."


_ARABIC_QTY_WORDS: dict[str, int] = {
    "واحد": 1,
    "واحدة": 1,
    "وحد": 1,
    "اثنين": 2,
    "اثنان": 2,
    "ثنتين": 2,
    "ثنين": 2,
    "تلاتة": 3,
    "ثلاثة": 3,
    "ثلاث": 3,
    "اربعة": 4,
    "أربعة": 4,
    "اربع": 4,
    "خمسة": 5,
    "خمس": 5,
    "ستة": 6,
    "ست": 6,
    "سبعة": 7,
    "سبع": 7,
    "ثمانية": 8,
    "ثمان": 8,
    "تسعة": 9,
    "تسع": 9,
    "عشرة": 10,
    "عشر": 10,
}


@dataclass(frozen=True)
class PendingEdit:
    kind: Literal["update_quantity", "add_items", "replace_items"]
    items: list[dict[str, Any]]
    target_line_index: int | None = None


def parse_quantity_from_text(text: str) -> int | None:
    from app.abuu.voice_interpretation.normalize import normalize_ordering_text

    normalized = normalize_ordering_text(str(text or "").strip(), language="ar")
    if not normalized:
        return None
    match = re.search(r"(\d+)", normalized)
    if match:
        return max(1, min(99, int(match.group(1))))
    tokens = normalized.split()
    for token in tokens:
        if token in _ARABIC_QTY_WORDS:
            return _ARABIC_QTY_WORDS[token]
    for word, qty in sorted(_ARABIC_QTY_WORDS.items(), key=lambda kv: -len(kv[0])):
        if word in normalized:
            return qty
    return None


def match_pending_item_line_index(
    pending_items: list[dict[str, Any]],
    text: str,
    lang: str,
) -> int | None:
    if not pending_items:
        return None
    if len(pending_items) == 1:
        return 1
    normalized = _normalized(text)
    if not normalized:
        return None
    best_idx: int | None = None
    best_len = 0
    for idx, row in enumerate(pending_items, start=1):
        if not isinstance(row, dict):
            continue
        for name in (row.get("name_ar"), row.get("name_en")):
            name_str = str(name or "").strip()
            if not name_str:
                continue
            name_norm = _normalized(name_str)
            if len(name_norm) < 2:
                continue
            if name_norm in normalized or normalized in name_norm:
                if len(name_norm) > best_len:
                    best_idx = idx
                    best_len = len(name_norm)
            else:
                tokens = [t for t in name_norm.split() if len(t) >= 3]
                hits = sum(1 for t in tokens if t in normalized)
                if hits >= 1 and len(name_norm) > best_len:
                    best_idx = idx
                    best_len = len(name_norm)
    return best_idx


def parse_pending_quantity_edit(
    text: str,
    pending: dict[str, Any],
    *,
    lang: str,
) -> PendingEdit | None:
    """Parse quantity update like 'بدي ثلاثة رز بالدجاج' against pending proposal."""
    from app.abuu.voice_interpretation.normalize import normalize_ordering_text

    normalized = normalize_ordering_text(str(text or "").strip(), language="ar")
    if not normalized:
        return None
    if is_affirmative_reply(text) or is_negative_reply(text) or is_cart_inquiry(text):
        return None
    from app.abuu.agent.menu_pick_parser import parse_menu_pick_tokens

    if parse_menu_pick_tokens(text):
        return None

    qty = parse_quantity_from_text(text)
    if qty is None:
        return None

    pending_items = pending.get("items") or []
    if not isinstance(pending_items, list) or not pending_items:
        return None

    line_idx = match_pending_item_line_index(pending_items, text, lang)
    if line_idx is None and len(pending_items) == 1:
        line_idx = 1
    if line_idx is None:
        return None

    row = pending_items[line_idx - 1]
    if not isinstance(row, dict):
        return None
    item_id = str(row.get("menu_item_id") or "").strip()
    if not item_id:
        return None
    return PendingEdit(
        kind="update_quantity",
        items=[{"menu_item_id": item_id, "quantity": qty}],
        target_line_index=line_idx,
    )


def _pending_items_as_proposal_rows(pending: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in pending.get("items") or []:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("menu_item_id") or "").strip()
        if not item_id:
            continue
        rows.append(
            {
                "menu_item_id": item_id,
                "quantity": max(1, int(row.get("quantity") or 1)),
            }
        )
    return rows


def apply_pending_edit(
    db: Session,
    session: AgentSession,
    *,
    edit: PendingEdit,
    lang: str,
) -> str:
    pending = get_pending_action(session)
    if pending is None:
        raise ValueError("No pending cart action")

    restaurant_id = str(pending.get("restaurant_id") or session.restaurant_id or "").strip()
    if not restaurant_id:
        raise ValueError("No restaurant for pending edit")

    current = _pending_items_as_proposal_rows(pending)
    merged: dict[str, int] = {row["menu_item_id"]: row["quantity"] for row in current}

    if edit.kind == "update_quantity" and edit.target_line_index is not None:
        for row in current:
            merged[row["menu_item_id"]] = row["quantity"]
        for raw in edit.items:
            item_id = str(raw.get("menu_item_id") or "").strip()
            qty = max(1, int(raw.get("quantity") or 1))
            if item_id:
                merged[item_id] = qty
    elif edit.kind == "replace_items":
        merged = {
            str(raw.get("menu_item_id") or "").strip(): max(1, int(raw.get("quantity") or 1))
            for raw in edit.items
            if str(raw.get("menu_item_id") or "").strip()
        }
    else:
        for raw in edit.items:
            item_id = str(raw.get("menu_item_id") or "").strip()
            qty = max(1, int(raw.get("quantity") or 1))
            if not item_id:
                continue
            merged[item_id] = merged.get(item_id, 0) + qty

    proposal_items = [{"menu_item_id": k, "quantity": v} for k, v in merged.items()]
    stored, total, delivery = build_proposal_lines(
        db,
        restaurant_id=restaurant_id,
        items=proposal_items,
        lang=lang,
    )
    set_pending_add_items(
        session,
        restaurant_id=restaurant_id,
        items=stored,
        total_agorot=total,
        delivery_fee_agorot=delivery,
        confirmation_question=confirmation_prompt(lang),
    )
    return format_proposal_message(
        db,
        restaurant_id=restaurant_id,
        items=proposal_items,
        lang=lang,
    )


def merge_pending_items(
    db: Session,
    session: AgentSession,
    *,
    new_items: list[dict[str, Any]],
    lang: str,
    replace: bool = False,
) -> str:
    kind: Literal["add_items", "replace_items"] = "replace_items" if replace else "add_items"
    return apply_pending_edit(
        db,
        session,
        edit=PendingEdit(kind=kind, items=new_items),
        lang=lang,
    )


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


def propose_menu_picks_from_text(
    db: Session,
    session: AgentSession,
    *,
    user_text: str,
    lang: str,
) -> str:
    from app.abuu.agent.menu_pick_parser import parse_menu_pick_tokens, resolve_menu_picks_to_items

    picks = parse_menu_pick_tokens(user_text)
    if not picks:
        raise ValueError("Invalid menu pick")

    menu_index = session.context.get("menu_item_index") or []
    if not isinstance(menu_index, list) or not menu_index:
        if lang == "ar":
            return "شوف المنيو أولاً واختار رقم الطبق."
        return "Please view the menu first, then send a dish number."

    items, invalid = resolve_menu_picks_to_items(menu_index, picks)
    if invalid:
        nums = ", ".join(str(n) for n in invalid)
        if lang == "ar":
            return f"رقم {nums} مو موجود بالمنيو. أرسل رقم من القائمة."
        return f"Number(s) {nums} are not on the menu. Pick from the list."

    if not items:
        if lang == "ar":
            return "ما لقيت أطباق. أرسل رقم من المنيو."
        return "No dishes found. Send a number from the menu."

    restaurant_id = str(session.restaurant_id or "").strip()
    if not restaurant_id:
        if lang == "ar":
            return "من أي مطعم بدك تطلب؟"
        return "Which restaurant would you like to order from?"

    stored, total, delivery = build_proposal_lines(
        db,
        restaurant_id=restaurant_id,
        items=items,
        lang=lang,
    )
    set_pending_add_items(
        session,
        restaurant_id=restaurant_id,
        items=stored,
        total_agorot=total,
        delivery_fee_agorot=delivery,
        confirmation_question=confirmation_prompt(lang),
    )
    return format_proposal_message(
        db,
        restaurant_id=restaurant_id,
        items=items,
        lang=lang,
    )
