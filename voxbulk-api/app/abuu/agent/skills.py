"""Agent tools — OpenAI function-calling handlers for DeepSeek."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.agent import kb as menu_kb
from app.abuu.agent.restaurant_webhook_service import post_restaurant_webhook
from app.abuu.agent.session import Session
from app.abuu.models.entities import CustomerOrder, DeliveryAssignment, Restaurant, RestaurantMenuItem
from app.abuu.services.addon_suggestion_service import suggest_addons
from app.abuu.services.agent_settings_service import is_skill_enabled
from app.abuu.services.customer_memory_service import apply_saved_address_to_order, save_customer_name
from app.abuu.services.kb_service import answer_kb_question, kb_fallback_message, resolve_settings
from app.abuu.services.location_service import get_default_address
from app.abuu.menu_intelligence.dietary_detector import DietaryDetector
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import (
    confirm_pending_payment_message,
    format_shekel,
    localized_name,
    order_status_message,
)
from app.abuu.agent.prefetch import restaurant_list_page_size
from app.abuu.agent.cart_resolver import add_offer_lines_to_order, resolve_cart_add_target
from app.abuu.agent.session_reset import clear_restaurant_binding
from app.abuu.services.offer_service import AbuuOfferService, format_offers_list
from app.abuu.services.restaurant_discovery_service import (
    format_restaurant_list,
    pick_restaurant_by_ref,
    rank_restaurants,
)
from app.abuu.services.skill_definitions import (
    SKILL_ANSWER_KB,
    SKILL_BUILD_CART,
    SKILL_CANCEL_OR_REFUND,
    SKILL_CONFIRM_ORDER,
    SKILL_HANDOFF_TO_ADMIN,
    SKILL_MENU_RECOMMEND,
    SKILL_ORDER_STATUS,
    SKILL_RESTAURANT_SEARCH,
    SKILL_SUGGEST_ADDONS,
)

logger = logging.getLogger(__name__)

TOOL_SKILL_MAP: dict[str, str] = {
    "search_menu": SKILL_MENU_RECOMMEND,
    "add_to_cart": SKILL_BUILD_CART,
    "remove_from_cart": SKILL_BUILD_CART,
    "get_cart": SKILL_BUILD_CART,
    "confirm_order": SKILL_CONFIRM_ORDER,
    "track_order": SKILL_ORDER_STATUS,
    "list_restaurants": SKILL_RESTAURANT_SEARCH,
    "select_restaurant": SKILL_RESTAURANT_SEARCH,
    "change_restaurant": SKILL_RESTAURANT_SEARCH,
    "list_offers": SKILL_RESTAURANT_SEARCH,
    "answer_policy": SKILL_ANSWER_KB,
    "cancel_order": SKILL_CANCEL_OR_REFUND,
    "escalate_to_admin": SKILL_HANDOFF_TO_ADMIN,
    "suggest_addons": SKILL_SUGGEST_ADDONS,
    "save_customer_name": SKILL_BUILD_CART,
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_menu",
        "description": "Find menu items by name or keyword. Always use before listing items.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_to_cart",
        "description": "Add a menu item to the cart.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 1},
                "notes": {"type": "string"},
            },
            "required": ["item_id"],
        },
    },
    {
        "name": "remove_from_cart",
        "description": "Remove an item from the cart.",
        "input_schema": {
            "type": "object",
            "properties": {"item_id": {"type": "string"}},
            "required": ["item_id"],
        },
    },
    {
        "name": "get_cart",
        "description": "Show current cart and total price.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "confirm_order",
        "description": "Finalize and place the order when the customer is ready.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "track_order",
        "description": "Check delivery status for an order.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
        },
    },
    {
        "name": "list_restaurants",
        "description": "List available restaurants. Do not filter by food type unless customer explicitly asks for one category only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: only when customer explicitly wants chicken-only or fish-only restaurants",
                },
            },
        },
    },
    {
        "name": "change_restaurant",
        "description": "Clear the current restaurant and show all available restaurants again.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_offers",
        "description": "List active promo offers. Use when customer asks about deals, promos, or discounts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional filter e.g. chicken, fish, عروض دجاج"},
            },
        },
    },
    {
        "name": "select_restaurant",
        "description": "Select a restaurant to order from. Accepts restaurant id, list number, or name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "restaurant_id": {"type": "string", "description": "Restaurant id, list number, or name"},
            },
            "required": ["restaurant_id"],
        },
    },
    {
        "name": "answer_policy",
        "description": "Answer policy questions: delivery fee, hours, refund, etc.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "cancel_order",
        "description": "Cancel the current draft or recent order.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "escalate_to_admin",
        "description": "Escalate to human support.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
        },
    },
    {
        "name": "suggest_addons",
        "description": "Suggest complementary sides or drinks after adding a main item.",
        "input_schema": {
            "type": "object",
            "properties": {"last_item_id": {"type": "string"}},
        },
    },
    {
        "name": "save_customer_name",
        "description": "Save the customer's first name for personalization.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]


def enabled_tool_schemas(db: Session) -> list[dict[str, Any]]:
    enabled: list[dict[str, Any]] = []
    for schema in TOOL_SCHEMAS:
        skill = TOOL_SKILL_MAP.get(schema["name"], schema["name"])
        if is_skill_enabled(db, skill):
            enabled.append(schema)
    return enabled


def to_openai_tools(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for schema in schemas:
        parameters = dict(schema.get("input_schema") or {"type": "object", "properties": {}})
        if parameters.get("type") == "object" and "properties" in parameters and "required" not in parameters:
            parameters["required"] = []
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema.get("description") or schema["name"],
                    "parameters": parameters,
                },
            }
        )
    return tools


def enabled_openai_tools(db: Session) -> list[dict[str, Any]]:
    return to_openai_tools(enabled_tool_schemas(db))


def _require_restaurant(session: Session) -> str:
    if not session.restaurant_id:
        raise ValueError("No restaurant selected. Use list_restaurants and select_restaurant first.")
    return session.restaurant_id


def _get_draft_order(db: Session, session: Session) -> CustomerOrder | None:
    if not session.active_order_id:
        return None
    order = db.get(CustomerOrder, session.active_order_id)
    if order is None or order.status != "draft":
        return None
    return order


def _resolve_kitchen_allergy_note(session: Session) -> str | None:
    ctx = session.context or {}
    existing = str(ctx.get("kitchen_allergy_note") or "").strip()
    if existing:
        return existing[:512]
    allergens = ctx.get("allergen_avoid")
    if isinstance(allergens, list) and allergens:
        return ("Allergy: " + ", ".join(str(a) for a in allergens))[:512]
    for msg in reversed(session.messages or []):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        dietary = DietaryDetector.detect(str(msg.get("content") or ""))
        if dietary.kitchen_note:
            return str(dietary.kitchen_note).strip()[:512]
    return None


def _refresh_cart(db: Session, session: Session, order: CustomerOrder | None) -> None:
    from app.abuu.agent.session import _cart_from_order

    session.cart = _cart_from_order(db, order)


def _format_menu_results(items: list[dict[str, Any]], lang: str) -> str:
    if not items:
        return "No matching items found."
    lines: list[str] = []
    for row in items:
        name = row["name_ar"] if lang == "ar" else row["name_en"]
        if not name:
            name = row["name_en"] or row["name_ar"]
        price = format_shekel(int(row.get("price_agorot") or row.get("price", 0) * 100))
        lines.append(f"- {name} ({price}) [id={row['id']}]")
    return "\n".join(lines)


class AgentSkills:
    def __init__(self, db: Session, session: Session, *, customer: Any) -> None:
        self.db = db
        self.session = session
        self.customer = customer
        self.lang = session.language or "ar"

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        skill = TOOL_SKILL_MAP.get(tool_name, tool_name)
        if not is_skill_enabled(self.db, skill):
            return "This action is not available right now. Please contact support."

        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            return f"Unknown tool: {tool_name}"
        try:
            return handler(tool_input or {})
        except ValueError as exc:
            return str(exc)
        except Exception:
            logger.exception(
                "abuu_agent_tool_failed tool=%s phone=%s restaurant=%s",
                tool_name,
                self.session.customer_wa_number,
                self.session.restaurant_id,
            )
            return "Something went wrong with that action. Please try again."

    def _tool_search_menu(self, inp: dict[str, Any]) -> str:
        restaurant_id = _require_restaurant(self.session)
        query = str(inp.get("query") or "").strip()
        items = menu_kb.search_menu(
            self.db,
            restaurant_id,
            query,
            self.lang,
            customer=self.customer,
        )
        return _format_menu_results(items, self.lang)

    def _tool_add_to_cart(self, inp: dict[str, Any]) -> str:
        restaurant_id = _require_restaurant(self.session)
        item_ref = str(inp.get("item_id") or "").strip()
        quantity = max(1, int(inp.get("quantity") or 1))
        notes = str(inp.get("notes") or "").strip()

        resolved = resolve_cart_add_target(
            self.db,
            restaurant_id=restaurant_id,
            ref=item_ref,
            session_context=self.session.context,
            lang=self.lang,
        )
        if resolved is None:
            raise ValueError(f"Item not found: {item_ref}")

        kind, target = resolved
        restaurant = self.db.get(Restaurant, restaurant_id)
        if restaurant is None:
            raise ValueError("Restaurant not found")
        order = _get_draft_order(self.db, self.session)
        if order is None:
            order = AbuuOrderDraftService.ensure_order(
                self.db,
                customer=self.customer,
                restaurant=restaurant,
                existing_order=None,
            )
            apply_saved_address_to_order(self.db, order, self.customer)
            self.session.active_order_id = order.id

        if kind == "offer":
            offer = target
            if offer.restaurant_id != restaurant_id:
                rest = self.db.get(Restaurant, offer.restaurant_id)
                rest_name = localized_name(rest, self.lang) if rest else offer.restaurant_id
                raise ValueError(
                    f"Offer belongs to {rest_name}. Switch restaurant first or say the restaurant name."
                )
            added = add_offer_lines_to_order(self.db, order, offer)
            if not added:
                raise ValueError("Offer items could not be added")
            title = offer.title_ar if self.lang == "ar" else (offer.title_en or offer.title_ar)
            summary_prefix = f"Added offer: {title}\n"
        else:
            item = target
            AbuuOrderDraftService.add_item(self.db, order, item, quantity=quantity)
            if notes:
                existing = order.notes or ""
                line_note = f"{localized_name(item, self.lang)}: {notes}"
                order.notes = f"{existing}\n{line_note}".strip() if existing else line_note
                self.db.add(order)
            summary_prefix = ""

        fingerprint = AbuuOrderDraftService.cart_fingerprint(self.db, order)
        self.session.context = AbuuOrderDraftService.mark_cart_changed(self.session.context, fingerprint)
        _refresh_cart(self.db, self.session, order)
        if kind == "menu_item":
            addon_hint, self.session.context = suggest_addons(
                self.db,
                restaurant_id=restaurant_id,
                main_item=target,
                active_categories=self.session.context.get("active_categories") or [],
                context=self.session.context,
                lang=self.lang,
            )
        else:
            addon_hint = None
        summary = summary_prefix + self._tool_get_cart({})
        if addon_hint:
            summary += f"\n\nSuggestion: {addon_hint}"
        return summary

    def _tool_remove_from_cart(self, inp: dict[str, Any]) -> str:
        order = _get_draft_order(self.db, self.session)
        if order is None:
            raise ValueError("Cart is empty")
        AbuuOrderDraftService.remove_item(
            self.db,
            order,
            item_id=str(inp.get("item_id") or ""),
        )
        _refresh_cart(self.db, self.session, order)
        return self._tool_get_cart({})

    def _tool_get_cart(self, _inp: dict[str, Any]) -> str:
        order = _get_draft_order(self.db, self.session)
        if order is None or not self.session.cart:
            return "Cart is empty."
        lines: list[str] = []
        for row in self.session.cart:
            price = format_shekel(int(row.get("price", 0) * 100))
            lines.append(f"- {row['name']} x{row['quantity']} ({price})")
        total = format_shekel(int(order.total_agorot or 0))
        if self.lang == "ar":
            return "السلة:\n" + "\n".join(lines) + f"\nالمجموع: {total}"
        return "Cart:\n" + "\n".join(lines) + f"\nTotal: {total}"

    def _tool_confirm_order(self, _inp: dict[str, Any]) -> str:
        order = _get_draft_order(self.db, self.session)
        if order is None:
            raise ValueError("Cart is empty")
        if order.total_agorot <= 0:
            raise ValueError("Cart is empty")
        fingerprint = AbuuOrderDraftService.cart_fingerprint(self.db, order)
        if self.session.context.get("confirmed_cart_fingerprint") == fingerprint:
            return confirm_pending_payment_message(order, self.lang)
        if not order.delivery_address_id:
            addr = get_default_address(self.db, self.customer.id)
            if addr is None:
                if self.lang == "ar":
                    return (
                        "يرجى إرسال موقع التوصيل (دبوس واتساب) قبل التأكيد. "
                        "Cannot confirm until delivery location is saved."
                    )
                return (
                    "Please send your delivery location as a WhatsApp location pin before confirming. "
                    "We need your address saved first."
                )
            order.delivery_address_id = addr.id
            order.location_missing = False
            self.db.add(order)
        AbuuOrderDraftService.confirm_draft(
            self.db,
            order,
            allergy_note=_resolve_kitchen_allergy_note(self.session),
        )
        self.session.context["confirmed_cart_fingerprint"] = fingerprint
        self.session.stage = "done"
        post_restaurant_webhook(order)
        order_id = order.id
        from app.abuu.agent.session import clear_session

        clear_session(self.db, self.session.customer_wa_number)
        self.session.active_order_id = order_id
        msg = confirm_pending_payment_message(order, self.lang)
        settings = resolve_settings(self.db, restaurant_id=order.restaurant_id)
        prep = settings.prep_minutes
        if prep:
            if self.lang == "ar":
                msg += f"\nالوقت المتوقع: ~{prep} دقيقة."
            else:
                msg += f"\nEstimated prep time: ~{prep} minutes."
        msg += f"\nOrder ID: {order_id}"
        return msg

    def _tool_track_order(self, inp: dict[str, Any]) -> str:
        order_id = str(inp.get("order_id") or self.session.active_order_id or "").strip()
        if not order_id:
            row = self.db.execute(
                select(CustomerOrder)
                .where(CustomerOrder.customer_id == self.customer.id)
                .order_by(CustomerOrder.created_at.desc())
            ).scalars().first()
            if row is None:
                raise ValueError("No order found")
            order_id = row.id
        order = self.db.get(CustomerOrder, order_id)
        if order is None:
            raise ValueError("Order not found")
        assignment = self.db.execute(
            select(DeliveryAssignment).where(DeliveryAssignment.order_id == order.id)
        ).scalar_one_or_none()
        return order_status_message(order, assignment, self.lang)

    def _tool_list_restaurants(self, inp: dict[str, Any]) -> str:
        prefetched = self.session.context.get("prefetched_restaurant_list")
        if isinstance(prefetched, str) and prefetched.strip():
            self.session.context.pop("prefetched_restaurant_list", None)
            return prefetched

        categories = inp.get("categories") if isinstance(inp.get("categories"), list) else None
        categories = [str(c).strip().lower() for c in (categories or []) if str(c).strip()] or None
        addr = get_default_address(self.db, self.customer.id)
        lat = addr.latitude if addr else None
        lng = addr.longitude if addr else None
        ranked = rank_restaurants(
            self.db,
            lat=lat,
            lng=lng,
            categories=categories,
            limit=15,
        )
        self.session.context["ranked_restaurants"] = [
            {"id": r.restaurant.id, "name_en": r.restaurant.name_en, "name_ar": r.restaurant.name_ar}
            for r in ranked
        ]
        return format_restaurant_list(
            ranked,
            lang=self.lang,
            page=0,
            page_size=restaurant_list_page_size(),
        )

    def _tool_change_restaurant(self, _inp: dict[str, Any]) -> str:
        clear_restaurant_binding(self.db, self.session)
        self.session.cart = []
        addr = get_default_address(self.db, self.customer.id)
        lat = addr.latitude if addr else None
        lng = addr.longitude if addr else None
        ranked = rank_restaurants(self.db, lat=lat, lng=lng, categories=None, limit=15)
        self.session.context["ranked_restaurants"] = [
            {"id": r.restaurant.id, "name_en": r.restaurant.name_en, "name_ar": r.restaurant.name_ar}
            for r in ranked
        ]
        listing = format_restaurant_list(
            ranked,
            lang=self.lang,
            page=0,
            page_size=restaurant_list_page_size(),
        )
        if self.lang == "ar":
            return f"تم. اختر مطعماً:\n{listing}"
        return f"Done. Pick a restaurant:\n{listing}"

    def _tool_list_offers(self, inp: dict[str, Any]) -> str:
        prefetched = self.session.context.get("prefetched_offers")
        if isinstance(prefetched, str) and prefetched.strip():
            self.session.context.pop("prefetched_offers", None)
            return prefetched

        from app.abuu.services.offer_service import categories_from_offer_query

        query = str(inp.get("query") or "").strip()
        categories = categories_from_offer_query(query) if query else None
        offers = AbuuOfferService.list_active(
            self.db,
            restaurant_id=self.session.restaurant_id,
            categories=categories,
            limit=15,
        )
        return format_offers_list(self.db, offers, lang=self.lang)

    def _tool_select_restaurant(self, inp: dict[str, Any]) -> str:
        ref = str(inp.get("restaurant_id") or "").strip()
        restaurant = self.db.get(Restaurant, ref)
        if restaurant is None:
            ranked_rows = self.session.context.get("ranked_restaurants") or []
            ranked = []
            for row in ranked_rows:
                if not isinstance(row, dict):
                    continue
                rest = self.db.get(Restaurant, row.get("id"))
                if rest is not None:
                    from app.abuu.services.restaurant_discovery_service import RankedRestaurant

                    ranked.append(RankedRestaurant(restaurant=rest, distance_km=0.0, match_score=0, is_open=rest.is_available))
            if not ranked:
                addr = get_default_address(self.db, self.customer.id)
                lat = addr.latitude if addr else None
                lng = addr.longitude if addr else None
                ranked = rank_restaurants(self.db, lat=lat, lng=lng, categories=None, limit=15)
            restaurant = pick_restaurant_by_ref(ranked, ref)
        if restaurant is None:
            raise ValueError("Restaurant not found")
        order = _get_draft_order(self.db, self.session)
        order = AbuuOrderDraftService.ensure_order(
            self.db,
            customer=self.customer,
            restaurant=restaurant,
            existing_order=order,
        )
        apply_saved_address_to_order(self.db, order, self.customer)
        self.session.restaurant_id = restaurant.id
        self.session.active_order_id = order.id
        self.session.context["restaurant_id"] = restaurant.id
        self.session.context["restaurant_selected"] = True
        name = localized_name(restaurant, self.lang)
        if self.lang == "ar":
            return f"تم اختيار {name}. ماذا تحب أن تأكل؟"
        return f"Selected {name}. What would you like to eat?"

    def _tool_answer_policy(self, inp: dict[str, Any]) -> str:
        topic = str(inp.get("topic") or "general").strip()
        settings = resolve_settings(self.db, restaurant_id=self.session.restaurant_id)
        answer = answer_kb_question(settings, topic, self.lang)
        return answer or kb_fallback_message(self.lang)

    def _tool_cancel_order(self, _inp: dict[str, Any]) -> str:
        order = _get_draft_order(self.db, self.session)
        if order is not None:
            AbuuOrderDraftService.cancel_draft(self.db, order)
            self.session.cart = []
            self.session.active_order_id = None
            clear_restaurant_binding(self.db, self.session)
            if self.lang == "ar":
                return "تم إلغاء الطلب. اكتب يلا ساي أو اعرض المطاعم للبدء من جديد."
            return "Order cancelled. Say yallasay or ask for restaurants to start fresh."
        if self.lang == "ar":
            return "لا يوجد طلب للإلغاء."
        return "No active order to cancel."

    def _tool_escalate_to_admin(self, inp: dict[str, Any]) -> str:
        settings = resolve_settings(self.db, restaurant_id=self.session.restaurant_id)
        reason = str(inp.get("reason") or "").strip()
        base = settings.escalation_rules_ar if self.lang == "ar" else settings.escalation_rules_en
        if reason:
            return f"{base}\n({reason})"
        return base or kb_fallback_message(self.lang)

    def _tool_suggest_addons(self, inp: dict[str, Any]) -> str:
        restaurant_id = _require_restaurant(self.session)
        item_id = str(inp.get("last_item_id") or "").strip()
        item = self.db.get(RestaurantMenuItem, item_id) if item_id else None
        if item is None:
            raise ValueError("Item not found")
        hint, self.session.context = suggest_addons(
            self.db,
            restaurant_id=restaurant_id,
            main_item=item,
            active_categories=self.session.context.get("active_categories") or [],
            context=self.session.context,
            lang=self.lang,
        )
        return hint or ("No add-on suggestions right now." if self.lang == "en" else "لا اقتراحات إضافية حالياً.")

    def _tool_save_customer_name(self, inp: dict[str, Any]) -> str:
        name = str(inp.get("name") or "").strip()
        if not name:
            raise ValueError("Name is required")
        save_customer_name(self.customer, name)
        self.db.add(self.customer)
        if self.lang == "ar":
            return f"تشرفنا {name.split()[0]}!"
        return f"Nice to meet you, {name.split()[0]}!"


def execute_tool(
    db: Session,
    session: Session,
    *,
    customer: Any,
    tool_name: str,
    tool_input: dict[str, Any] | str,
) -> str:
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except json.JSONDecodeError:
            tool_input = {}
    skills = AgentSkills(db, session, customer=customer)
    return skills.execute(tool_name, tool_input or {})
