"""Shared pending-state turn resolution for agent router and orchestrator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.abuu.agent.menu_pick_parser import parse_menu_pick_tokens, resolve_menu_picks_to_items
from app.abuu.agent.menu_selection import store_shown_menu
from app.abuu.agent.gaza_context import refresh_menu_item_index
from app.abuu.agent.pending_action import (
    apply_pending_add_items,
    apply_pending_edit,
    clear_transactional_context,
    format_cart_summary_for_session,
    get_pending_action,
    is_cart_inquiry,
    is_explicit_flow_exit,
    merge_pending_items,
    parse_pending_quantity_edit,
    pending_edit_hint,
    score_pending_intent,
)
from app.abuu.agent.session import Session as AgentSession
from app.abuu.agent.usage_help import is_usage_help_request
from app.abuu.menu_intelligence.dietary_detector import DietaryDetector
from app.abuu.models.entities import CustomerProfile, Restaurant
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.preference_service import category_label, match_food_categories
from app.abuu.services.reply_service import format_shekel, localized_name
from app.abuu.services.intent_service import is_restaurant_list_message

ConversationState = Literal["browsing", "cart_confirmation", "ordering", "checkout"]
TurnIntent = Literal[
    "confirm",
    "cancel",
    "cart_inquiry",
    "menu_pick",
    "qty_edit",
    "correction_pivot",
    "dietary_filter",
    "usage_help",
    "exit_flow",
    "restaurant_switch",
    "defer",
]
PendingAction = Literal[
    "confirm_pending",
    "cancel_pending",
    "show_cart",
    "update_pending_quantity",
    "add_more_items_to_pending",
    "replace_pending_items",
    "correction_food_search",
    "usage_help",
    "pending_clarify",
    "defer",
]

_CORRECTION_PREFIX = re.compile(
    r"^(?:لا|مو|not|no|بديش|بدون|instead|rather)\b",
    re.I,
)
_ADD_MORE_MARKERS = re.compile(
    r"(?:كمان|also|too|اضف|أضف|add|مع|plus|\+)",
    re.I,
)


@dataclass(frozen=True)
class PendingTurnDecision:
    action: PendingAction
    branch: str
    reply: str | None = None


def derive_state(session: AgentSession) -> ConversationState:
    flow = str(session.context.get("active_flow") or "").strip()
    if flow == "checkout":
        return "checkout"
    if get_pending_action(session) is not None:
        return "cart_confirmation"
    if flow in {"ordering", "cart_confirmation"}:
        return "ordering" if flow == "ordering" else "cart_confirmation"
    if session.cart:
        return "ordering"
    return "browsing"


def _normalized(text: str) -> str:
    from app.abuu.voice_interpretation.normalize import normalize_query

    return normalize_query(str(text or "").strip(), "ar")


def is_correction_pivot(text: str) -> bool:
    normalized = _normalized(text)
    if not normalized:
        return False
    if _ADD_MORE_MARKERS.search(normalized):
        return False
    if _CORRECTION_PREFIX.search(normalized):
        return bool(match_food_categories(text))
    neg_patterns = (
        r"\b(?:no|not)\s+(?:chicken|fish|meat|dessert|salad|drinks?)\b",
        r"\b(?:مو|بدون|بديش)\s+(?:دجاج|سمك|لحم|حلو|سلطة|مشروب)",
    )
    for pattern in neg_patterns:
        if re.search(pattern, normalized, re.I):
            return True
    return False


def classify_turn_intent(
    text: str,
    session: AgentSession,
    *,
    state: ConversationState | None = None,
) -> TurnIntent:
    current_state = state or derive_state(session)
    from app.abuu.agent.intent_gate import is_menu_browse_request

    if is_usage_help_request(text):
        return "usage_help"
    if is_explicit_flow_exit(text) or is_restaurant_list_message(text):
        return "exit_flow"

    menu_browse = is_menu_browse_request(text) or bool(
        re.search(r"منيو|قائمة|menu", _normalized(text), re.I)
    )

    pending = get_pending_action(session)
    if pending is not None or current_state == "cart_confirmation":
        intent_name, confidence = score_pending_intent(text, menu_browse=menu_browse)
        if confidence >= 0.45:
            mapping: dict[str, TurnIntent] = {
                "confirm": "confirm",
                "cancel": "cancel",
                "cart": "cart_inquiry",
                "qty_edit": "qty_edit",
                "add_items": "menu_pick",
                "correction": "correction_pivot",
            }
            mapped = mapping.get(intent_name)
            if mapped:
                return mapped

    if is_cart_inquiry(text, menu_browse=menu_browse):
        return "cart_inquiry"

    if pending is not None:
        if parse_pending_quantity_edit(text, pending, lang=session.language or "ar"):
            return "qty_edit"
        if is_correction_pivot(text):
            return "correction_pivot"
        dietary = DietaryDetector.detect(text)
        if dietary.allergens_avoid or dietary.dietary_tags:
            return "dietary_filter"

    if current_state == "cart_confirmation":
        if parse_menu_pick_tokens(text):
            return "menu_pick"
    elif session.restaurant_id and parse_menu_pick_tokens(text):
        return "menu_pick"

    return "defer"


def _run_correction_food_search(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    text: str,
    lang: str,
) -> str:
    clear_transactional_context(session)
    session.context["last_query_text"] = text
    session.context["active_flow"] = "browsing"

    categories = match_food_categories(text)
    dietary = DietaryDetector.detect(text)
    if dietary.allergens_avoid:
        session.context["allergen_avoid"] = dietary.allergens_avoid
    if dietary.dietary_tags:
        session.context["dietary_tags"] = dietary.dietary_tags

    restaurant_id = str(session.restaurant_id or session.context.get("bound_restaurant_id") or "").strip()
    if not restaurant_id:
        if lang == "ar":
            return "من أي مطعم بدك؟ اكتب اسم المطعم أو قول اعرض المطاعم."
        return "Which restaurant? Say a name or ask for the list."

    restaurant = db.get(Restaurant, restaurant_id)
    if restaurant is None:
        if lang == "ar":
            return "ما لقيت المطعم. جرّب مرة ثانية."
        return "Restaurant not found. Try again."

    from app.abuu.agent.menu_selection import session_menu_filters

    allergen_avoid, dietary_required = session_menu_filters(session)
    items = AbuuOrderDraftService.list_menu_items(
        db,
        restaurant_id,
        categories=categories or None,
        limit=12,
        customer=customer,
        allergen_avoid=allergen_avoid or None,
        dietary_required=dietary_required or None,
        query_text=text,
    )
    if not items:
        cat_label = category_label(categories[0], lang) if categories else text
        if lang == "ar":
            return f"ما لقيت {cat_label} بهالمطعم. جرّب طلب ثاني أو شوف المنيو."
        return f"No {cat_label} found at this restaurant. Try another request or browse the menu."

    store_shown_menu(session, items, source="correction_search")
    rest_name = localized_name(restaurant, lang)
    lines: list[str] = []
    if lang == "ar":
        lines.append(f"تمام، هذي خيارات {rest_name}:")
    else:
        lines.append(f"OK — options from {rest_name}:")
    for idx, item in enumerate(items[:12], start=1):
        lines.append(f"{idx}. {localized_name(item, lang)} — {format_shekel(item.price_agorot)}")
    if lang == "ar":
        lines.append("\nأرسل رقم الطبق أو 1 2 3 لإضافة أكثر من واحد.")
    else:
        lines.append("\nSend a dish number or 1 2 3 to add multiple.")
    return "\n".join(lines)


def execute_pending_turn(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    user_text: str,
    decision: PendingTurnDecision,
) -> str:
    lang = session.language or "ar"
    action = decision.action

    if decision.reply is not None:
        return decision.reply

    if action == "confirm_pending":
        try:
            return apply_pending_add_items(db, session, customer=customer)
        except ValueError as exc:
            return str(exc) or ("ما قدرت أضيف للسلة." if lang == "ar" else "Could not add to cart.")

    if action == "cancel_pending":
        clear_transactional_context(session)
        return "تمام، ما أضفتهم. شو بدك تطلب؟" if lang == "ar" else "OK, I didn't add them. What would you like?"

    if action == "show_cart":
        return format_cart_summary_for_session(db, session, lang)

    if action == "usage_help":
        from app.abuu.agent.usage_help import usage_guide_ar

        return usage_guide_ar()

    if action == "pending_clarify":
        return pending_edit_hint(lang)

    if action == "correction_food_search":
        return _run_correction_food_search(db, session, customer=customer, text=user_text, lang=lang)

    pending = get_pending_action(session)
    if pending is None:
        return pending_edit_hint(lang)

    if action == "update_pending_quantity":
        edit = parse_pending_quantity_edit(user_text, pending, lang=lang)
        if edit is None:
            return pending_edit_hint(lang)
        try:
            return apply_pending_edit(db, session, edit=edit, lang=lang)
        except ValueError as exc:
            return str(exc) or pending_edit_hint(lang)

    if action in {"add_more_items_to_pending", "replace_pending_items"}:
        picks = parse_menu_pick_tokens(user_text)
        menu_index = session.context.get("menu_item_index") or []
        if not picks:
            return pending_edit_hint(lang)
        if not isinstance(menu_index, list) or not menu_index:
            refresh_menu_index = session.restaurant_id or str(pending.get("restaurant_id") or "")
            if refresh_menu_index:
                from app.abuu.agent.gaza_context import refresh_menu_item_index

                refresh_menu_item_index(
                    db,
                    session,
                    restaurant_id=str(refresh_menu_index),
                    lang=lang,
                )
                menu_index = session.context.get("menu_item_index") or []
        if not menu_index:
            if lang == "ar":
                return "شوف المنيو أولاً واختار رقم الطبق."
            return "View the menu first, then send dish numbers."
        items, invalid = resolve_menu_picks_to_items(menu_index, picks)
        if invalid:
            nums = ", ".join(str(n) for n in invalid)
            if lang == "ar":
                return f"رقم {nums} مو موجود بالمنيو. أرسل رقم من القائمة."
            return f"Number(s) {nums} are not on the menu."
        if not items:
            return pending_edit_hint(lang)
        try:
            return merge_pending_items(
                db,
                session,
                new_items=items,
                lang=lang,
                replace=action == "replace_pending_items",
            )
        except ValueError as exc:
            return str(exc) or pending_edit_hint(lang)

    return pending_edit_hint(lang)


def resolve_pending_turn(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    user_text: str,
    ranked_rows: list[dict[str, Any]] | None = None,
) -> PendingTurnDecision | None:
    """Resolve a turn when pending_action exists; None if no pending."""
    del ranked_rows
    pending = get_pending_action(session)
    if pending is None:
        return None

    lang = session.language or "ar"
    intent = classify_turn_intent(user_text, session, state="cart_confirmation")

    if intent == "exit_flow":
        clear_transactional_context(session)
        return PendingTurnDecision("defer", "pending_cleared_exit")

    if intent == "confirm":
        return PendingTurnDecision("confirm_pending", "transactional_pending_confirmed")

    if intent == "cancel":
        return PendingTurnDecision("cancel_pending", "transactional_pending_cancelled")

    if intent == "cart_inquiry":
        return PendingTurnDecision("show_cart", "transactional_pending_cart_summary")

    if intent == "usage_help":
        return PendingTurnDecision("usage_help", "transactional_pending_usage_help")

    if intent == "correction_pivot":
        return PendingTurnDecision("correction_food_search", "transactional_pending_correction")

    if intent == "dietary_filter":
        dietary = DietaryDetector.detect(user_text)
        if dietary.allergens_avoid:
            session.context["allergen_avoid"] = dietary.allergens_avoid
        if dietary.dietary_tags:
            session.context["dietary_tags"] = dietary.dietary_tags
        if match_food_categories(user_text) or is_correction_pivot(user_text):
            return PendingTurnDecision("correction_food_search", "transactional_pending_dietary_filter")
        return PendingTurnDecision("pending_clarify", "transactional_pending_dietary_only")

    if intent == "qty_edit":
        return PendingTurnDecision("update_pending_quantity", "transactional_pending_qty_edit")

    if intent == "menu_pick":
        picks = parse_menu_pick_tokens(user_text)
        pending_items = pending.get("items") or []
        if picks and len(pending_items) == 1 and len(picks) == 1 and picks[0][1] > 1:
            row = pending_items[0]
            item_id = str(row.get("menu_item_id") or "").strip()
            qty = max(1, int(picks[0][1]))
            if item_id:
                from app.abuu.agent.pending_action import PendingEdit

                try:
                    reply = apply_pending_edit(
                        db,
                        session,
                        edit=PendingEdit(
                            kind="update_quantity",
                            items=[{"menu_item_id": item_id, "quantity": qty}],
                            target_line_index=1,
                        ),
                        lang=lang,
                    )
                    return PendingTurnDecision(
                        "update_pending_quantity",
                        "transactional_pending_qty_token",
                        reply=reply,
                    )
                except ValueError:
                    pass

        if picks:
            return PendingTurnDecision("add_more_items_to_pending", "transactional_pending_add_items")

        return PendingTurnDecision("pending_clarify", "transactional_pending_invalid_pick")

    return PendingTurnDecision("pending_clarify", "transactional_pending_clarify")


def resolve_and_execute_pending_turn(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    user_text: str,
    ranked_rows: list[dict[str, Any]] | None = None,
) -> tuple[str, str, PendingAction] | None:
    """Resolve pending turn and execute; None if no pending or defer after clear."""
    decision = resolve_pending_turn(
        db,
        session,
        customer=customer,
        user_text=user_text,
        ranked_rows=ranked_rows,
    )
    if decision is None:
        return None
    if decision.action == "defer":
        return None
    reply = execute_pending_turn(
        db,
        session,
        customer=customer,
        user_text=user_text,
        decision=decision,
    )
    return reply, decision.branch, decision.action
