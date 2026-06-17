"""Single turn router — classify slots once, apply fixed priority, execute one action."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.abuu.agent.gaza_context import refresh_menu_item_index
from app.abuu.agent.intent_gate import (
    AgentIntent,
    apply_restaurant_selection,
    cart_cleared_notice,
    extract_intent,
    find_named_restaurant_in_text,
    format_restaurant_menu,
    freeze_turn_restaurant_snapshot,
    is_menu_browse_request,
    phase1_enabled,
    ranked_from_snapshot,
    try_category_without_restaurant_reply,
)
from app.abuu.agent.menu_pick_parser import is_menu_pick_message
from app.abuu.agent.pending_action import (
    apply_pending_add_items,
    clear_transactional_context,
    format_cart_summary_for_session,
    get_pending_action,
    has_explicit_cart_noun,
    is_affirmative_reply,
    is_cart_inquiry,
    is_explicit_flow_exit,
    is_negative_reply,
    is_transactional_flow,
    propose_menu_picks_from_text,
)
from app.abuu.agent.prefetch import prefetch_restaurant_list
from app.abuu.agent.session import Session as AgentSession
from app.abuu.agent.session_reset import is_offer_query
from app.abuu.agent.usage_help import is_usage_help_request
from app.abuu.models.entities import CustomerProfile, Restaurant
from app.abuu.services.intent_service import is_restaurant_list_message
from app.abuu.services.reply_service import localized_name, menu_keyboard_hint, usage_guide_ar


def _menu_browse_slot(text: str) -> bool:
    if has_explicit_cart_noun(text):
        return False
    from app.abuu.voice_interpretation.normalize import normalize_query

    normalized = normalize_query(str(text or ""), "ar")
    if re.search(r"منيو|قائمة|menu", normalized, re.I):
        return True
    return is_menu_browse_request(text)


TurnAction = Literal[
    "pending_confirm",
    "pending_cancel",
    "pending_clarify",
    "switch_and_menu",
    "switch_restaurant",
    "cart_summary",
    "restaurant_list",
    "menu_clarify",
    "category_clarify",
    "usage_help",
    "propose_menu_items",
    "defer_llm",
]


@dataclass(frozen=True)
class TurnSlots:
    restaurant_id: str | None = None
    menu_browse: bool = False
    cart_status: bool = False
    offer_browse: bool = False
    restaurant_list: bool = False
    exit_flow: bool = False
    numeric_only: bool = False
    confirm_pending: bool | None = None
    has_menu_item_index: bool = False
    menu_pick: bool = False
    usage_help: bool = False
    intent_action: str = "none"
    intent_confidence: str = "low"

    def to_debug_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TurnDecision:
    action: TurnAction
    branch: str
    slots: TurnSlots
    restaurant_id: str | None = None


def _is_numeric_only_message(text: str) -> bool:
    from app.abuu.agent.intent_gate import _is_numeric_restaurant_ref, _normalize_numeric_ref

    stripped = str(text or "").strip()
    if not stripped:
        return False
    ref = _normalize_numeric_ref(stripped)
    ascii_digits = stripped.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).strip()
    return ref == ascii_digits and _is_numeric_restaurant_ref(ref)


def classify_turn(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    user_text: str,
    ranked_rows: list[dict[str, Any]],
) -> tuple[TurnSlots, AgentIntent]:
    del customer
    ranked = ranked_from_snapshot(db, ranked_rows)
    menu_browse = _menu_browse_slot(user_text)
    offer_browse = is_offer_query(user_text)
    restaurant_list = is_restaurant_list_message(user_text)
    exit_flow = is_explicit_flow_exit(user_text)
    cart_status = is_cart_inquiry(user_text, menu_browse=menu_browse)

    named = find_named_restaurant_in_text(db, user_text, ranked)
    intent = extract_intent(db, text=user_text, ranked=ranked, session=session)

    pending = get_pending_action(session)
    confirm_pending: bool | None = None
    if pending is not None:
        if is_affirmative_reply(user_text):
            confirm_pending = True
        elif is_negative_reply(user_text):
            confirm_pending = False

    menu_index = session.context.get("menu_item_index")
    has_menu_item_index = isinstance(menu_index, list) and len(menu_index) > 0
    menu_pick = bool(session.restaurant_id and is_menu_pick_message(user_text))

    return (
        TurnSlots(
            restaurant_id=intent.restaurant_id or (named.id if named else None),
            menu_browse=menu_browse,
            cart_status=cart_status,
            offer_browse=offer_browse,
            restaurant_list=restaurant_list,
            exit_flow=exit_flow,
            numeric_only=_is_numeric_only_message(user_text),
            confirm_pending=confirm_pending,
            has_menu_item_index=has_menu_item_index,
            menu_pick=menu_pick,
            usage_help=is_usage_help_request(user_text),
            intent_action=intent.action,
            intent_confidence=intent.confidence,
        ),
        intent,
    )


def resolve_turn(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    user_text: str,
    ranked_rows: list[dict[str, Any]],
) -> TurnDecision:
    slots, intent = classify_turn(db, session, customer=customer, user_text=user_text, ranked_rows=ranked_rows)
    pending = get_pending_action(session)
    transactional = is_transactional_flow(session)

    if pending is not None:
        switching = bool(
            slots.restaurant_id
            and slots.menu_browse
            and (not session.restaurant_id or slots.restaurant_id != session.restaurant_id)
        )
        if switching or slots.exit_flow or slots.restaurant_list:
            clear_transactional_context(session)
        elif slots.confirm_pending is True:
            return TurnDecision("pending_confirm", "transactional_pending_confirmed", slots)
        elif slots.confirm_pending is False:
            return TurnDecision("pending_cancel", "transactional_pending_cancelled", slots)
        elif slots.cart_status:
            return TurnDecision("cart_summary", "transactional_pending_cart_summary", slots)
        else:
            return TurnDecision("pending_clarify", "transactional_pending_clarify", slots)

    if slots.usage_help:
        return TurnDecision("usage_help", "turn_usage_help", slots)

    if slots.menu_pick and session.restaurant_id and slots.has_menu_item_index:
        return TurnDecision("propose_menu_items", "turn_propose_menu_items", slots)

    if intent.confidence == "high" and intent.action == "select_restaurant_and_show_menu":
        return TurnDecision(
            "switch_and_menu",
            "phase1_select_and_menu",
            slots,
            restaurant_id=intent.restaurant_id,
        )
    if intent.confidence == "high" and intent.action == "select_restaurant":
        return TurnDecision(
            "switch_restaurant",
            "phase1_select",
            slots,
            restaurant_id=intent.restaurant_id,
        )

    if not session.restaurant_id and slots.restaurant_list:
        return TurnDecision("restaurant_list", "phase1_restaurant_list", slots)

    if slots.cart_status and not slots.menu_browse:
        if transactional or has_explicit_cart_noun(user_text):
            branch = "transactional_cart_summary" if transactional else "phase1_cart_summary"
            return TurnDecision("cart_summary", branch, slots)

    if slots.offer_browse and not slots.menu_browse and not slots.cart_status:
        return TurnDecision("defer_llm", "turn_defer_offer", slots)

    if intent.action == "show_menu" and intent.confidence == "low" and not session.restaurant_id:
        if transactional and not slots.exit_flow:
            return TurnDecision("defer_llm", "turn_defer_transactional", slots)
        return TurnDecision("menu_clarify", "phase1_menu_clarify", slots)

    if intent.confidence != "high" or intent.action == "none":
        category_reply = try_category_without_restaurant_reply(
            db, session, user_text=user_text, ranked_rows=ranked_rows
        )
        if category_reply is not None:
            if transactional and not slots.exit_flow:
                return TurnDecision("defer_llm", "turn_defer_transactional", slots)
            return TurnDecision("category_clarify", "phase1_category_clarify", slots)

    return TurnDecision("defer_llm", "turn_defer_llm", slots)


def execute_turn_decision(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    user_text: str,
    decision: TurnDecision,
    ranked_rows: list[dict[str, Any]],
) -> str | None:
    lang = session.language or "ar"
    action = decision.action

    if action == "defer_llm":
        return None

    if action == "usage_help":
        return usage_guide_ar()

    if action == "propose_menu_items":
        return propose_menu_picks_from_text(db, session, user_text=user_text, lang=lang)

    if action == "pending_confirm":
        try:
            return apply_pending_add_items(db, session, customer=customer)
        except ValueError as exc:
            return str(exc) or ("ما قدرت أضيف للسلة." if lang == "ar" else "Could not add to cart.")

    if action == "pending_cancel":
        clear_transactional_context(session)
        return "تمام، ما أضفتهم. شو بدك تطلب؟" if lang == "ar" else "OK, I didn't add them. What would you like?"

    if action == "pending_clarify":
        return (
            "ما فهمت تأكيدك. قول نعم أو لا، أو اسأل عن السلة."
            if lang == "ar"
            else "I didn't catch that. Say yes or no, or ask about your cart."
        )

    if action == "cart_summary":
        return format_cart_summary_for_session(db, session, lang)

    if action == "restaurant_list":
        session.context["awaiting_restaurant_pick"] = True
        session.context["awaiting_dish_pick"] = False
        session.context["last_list_type"] = "restaurant"
        listing = session.context.get("prefetched_restaurant_list")
        if isinstance(listing, str) and listing.strip():
            return listing
        return None

    if action == "menu_clarify":
        if lang == "ar":
            return "من أي مطعم بدك تشوف المنيو؟ اكتب اسم المطعم أو قول اعرض المطاعم."
        return "Which restaurant menu should I show? Say the restaurant name or ask for the list."

    if action == "category_clarify":
        return try_category_without_restaurant_reply(
            db, session, user_text=user_text, ranked_rows=ranked_rows
        )

    restaurant_id = decision.restaurant_id
    if not restaurant_id:
        return None
    restaurant = db.get(Restaurant, restaurant_id)
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

    if action == "switch_and_menu":
        menu_body, _items = refresh_menu_item_index(
            db,
            session,
            restaurant_id=restaurant.id,
            lang=lang,
        )
        if not menu_body:
            menu_body = format_restaurant_menu(
                db,
                restaurant_id=restaurant.id,
                lang=lang,
                customer=customer,
            )
        hint = menu_keyboard_hint(lang)
        if lang == "ar":
            return f"{prefix}هذا منيو {name}:\n{menu_body}{hint}"
        return f"{prefix}Here is the menu for {name}:\n{menu_body}{hint}"

    if action == "switch_restaurant":
        if lang == "ar":
            return f"{prefix}تم اختيار {name}. ماذا تحب أن تأكل؟"
        return f"{prefix}Selected {name}. What would you like to eat?"

    return None


def try_turn_router_reply(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    user_text: str,
) -> tuple[str, str, dict[str, Any]] | None:
    if not phase1_enabled():
        return None

    if not session.context.get("prefetched_restaurant_list") and not session.restaurant_id:
        prefetch_restaurant_list(db, session, customer_id=customer.id)

    ranked_rows = freeze_turn_restaurant_snapshot(db, session, customer_id=customer.id)
    decision = resolve_turn(
        db,
        session,
        customer=customer,
        user_text=user_text,
        ranked_rows=ranked_rows,
    )
    slots_debug = decision.slots.to_debug_dict()
    slots_debug["turn_action"] = decision.action

    reply = execute_turn_decision(
        db,
        session,
        customer=customer,
        user_text=user_text,
        decision=decision,
        ranked_rows=ranked_rows,
    )
    if reply is None:
        return None

    return reply, decision.branch, slots_debug
