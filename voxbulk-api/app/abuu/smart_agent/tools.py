"""Smart Waiter Agent tools — tag-aware, bulk-cart, persisted allergies, single-source confirm."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.agent import kb as menu_kb
from app.abuu.agent.prefetch import restaurant_list_page_size
from app.abuu.agent.restaurant_webhook_service import post_restaurant_webhook
from app.abuu.agent.session import Session as AgentSession
from app.abuu.agent.session_reset import clear_restaurant_binding
from app.abuu.menu_intelligence.dietary_detector import DietaryDetector
from app.abuu.menu_intelligence.safety_filter import MenuSafetyFilter
from app.abuu.menu_intelligence.vocabulary import (
    ALLERGEN_TAGS,
    DIETARY_TAGS,
    PROTEIN_TAGS,
    RECIPE_TAGS,
    parse_json_tags,
)
from app.abuu.models.entities import (
    CustomerOrder,
    CustomerProfile,
    DeliveryAssignment,
    Restaurant,
    RestaurantMenuItem,
)
from app.abuu.services.addon_suggestion_service import suggest_addons
from app.abuu.services.customer_memory_service import (
    apply_saved_address_to_order,
    save_customer_name,
)
from app.abuu.services.kb_service import (
    answer_kb_question,
    kb_fallback_message,
    resolve_settings,
)
from app.abuu.services.location_service import get_default_address
from app.abuu.services.notification_service import AbuuNotificationService
from app.abuu.services.offer_service import (
    AbuuOfferService,
    categories_from_offer_query,
    format_offers_list,
)
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.order_service import AbuuOrderService
from app.abuu.services.reply_service import (
    confirm_pending_payment_message,
    format_shekel,
    localized_name,
    order_sent_to_restaurant_message,
    order_status_message,
)
from app.abuu.services.restaurant_discovery_service import (
    format_restaurant_list,
    pick_restaurant_by_ref,
    rank_restaurants,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Tool schemas (OpenAI-style)
# --------------------------------------------------------------------------- #

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_menu",
        "description": (
            "Search this restaurant's menu by name/keyword (e.g. شاورما, دجاج, fish). "
            "Returns up to 6 items with id, name, price, and tags "
            "(allergens, dietary, recipe, protein) so you can recommend safely and explain why."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term in Arabic or English"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 6},
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_to_cart",
        "description": (
            "Add one OR multiple items to the cart in a single call. "
            "Use items array for multi-item turns like 'تنين شاورما وكولا'. "
            "item_id MUST come from search_menu results — never invent IDs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "List of items to add in this turn.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item_id": {"type": "string"},
                            "quantity": {"type": "integer", "minimum": 1, "default": 1},
                            "notes": {"type": "string", "description": "Free-text customisation (بدون بصل, حار, …)"},
                        },
                        "required": ["item_id"],
                    },
                },
            },
            "required": ["items"],
        },
    },
    {
        "name": "remove_from_cart",
        "description": "Remove an item from the cart by its item_id.",
        "parameters": {
            "type": "object",
            "properties": {"item_id": {"type": "string"}},
            "required": ["item_id"],
        },
    },
    {
        "name": "get_cart",
        "description": "Show the current cart and total.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "set_allergy",
        "description": (
            "Persist customer allergies / dietary preferences. Use as soon as the customer mentions "
            "an allergy or diet (no dairy, vegan, gluten-free, …). Stored on the customer profile "
            "and applied to all future menu searches."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "allergens": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": sorted(ALLERGEN_TAGS),
                    },
                    "description": "Canonical allergen tags to avoid",
                },
                "dietary": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": sorted(DIETARY_TAGS),
                    },
                    "description": "Required dietary tags",
                },
                "note": {"type": "string", "description": "Free-text note to attach to the kitchen on confirm"},
            },
        },
    },
    {
        "name": "confirm_order",
        "description": (
            "Finalize the cart and send the order to the restaurant. Only call when the customer "
            "has explicitly agreed (e.g. 'تأكيد', 'اطلب'). Requires a saved delivery address — "
            "ask for a WhatsApp location pin first if missing."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_restaurants",
        "description": "List restaurants available to this customer. Use when no restaurant is selected.",
        "parameters": {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: filter to a single category if customer asked for it",
                },
            },
        },
    },
    {
        "name": "select_restaurant",
        "description": "Bind the customer to a restaurant. Accepts list number, id, or name.",
        "parameters": {
            "type": "object",
            "properties": {"restaurant_id": {"type": "string"}},
            "required": ["restaurant_id"],
        },
    },
    {
        "name": "change_restaurant",
        "description": "Clear the currently bound restaurant and show all restaurants again.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_offers",
        "description": "List active promo offers. Use when the customer asks about deals/discounts.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        },
    },
    {
        "name": "answer_policy",
        "description": "Answer policy questions (hours, delivery fee, prep time, refund, …).",
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "cancel_order",
        "description": "Cancel the current draft order or recent order.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "escalate_to_admin",
        "description": "Escalate the conversation to human support with a reason.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
        },
    },
    {
        "name": "save_customer_name",
        "description": "Save the customer's first name for personalisation.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "track_order",
        "description": "Check delivery status of an order.",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
        },
    },
]


def openai_tools() -> list[dict[str, Any]]:
    """Convert tool schemas to OpenAI function-calling format."""
    out: list[dict[str, Any]] = []
    for schema in TOOL_SCHEMAS:
        params = dict(schema.get("parameters") or {"type": "object", "properties": {}})
        if params.get("type") == "object" and "required" not in params:
            params["required"] = []
        out.append(
            {
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema.get("description") or schema["name"],
                    "parameters": params,
                },
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Allergy persistence helpers
# --------------------------------------------------------------------------- #


def _parse_customer_list_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip().lower() for x in data if str(x).strip()]


def _persist_customer_safety(
    db: Session,
    customer: CustomerProfile,
    *,
    allergens: list[str],
    dietary: list[str],
) -> None:
    existing_allergens = set(_parse_customer_list_json(customer.allergens_json))
    existing_dietary = set(_parse_customer_list_json(customer.dietary_json))
    merged_allergens = sorted(existing_allergens | {a.lower() for a in allergens if a})
    merged_dietary = sorted(existing_dietary | {d.lower() for d in dietary if d})
    if merged_allergens:
        customer.allergens_json = json.dumps(merged_allergens)
    if merged_dietary:
        customer.dietary_json = json.dumps(merged_dietary)
    if merged_allergens or merged_dietary:
        db.add(customer)


def load_customer_safety(customer: CustomerProfile | None) -> tuple[list[str], list[str]]:
    """Return (allergens, dietary) saved on the customer profile."""
    if customer is None:
        return [], []
    return (
        _parse_customer_list_json(customer.allergens_json),
        _parse_customer_list_json(customer.dietary_json),
    )


def hydrate_safety_into_session(
    session: AgentSession,
    customer: CustomerProfile | None,
    *,
    text: str | None = None,
) -> None:
    """Merge persisted + detected allergens into session.context (idempotent)."""
    persisted_allergens, persisted_dietary = load_customer_safety(customer)
    session_allergens = list(session.context.get("allergen_avoid") or [])
    session_dietary = list(session.context.get("dietary_tags") or [])
    note = session.context.get("kitchen_allergy_note")

    if text:
        det = DietaryDetector.detect(text)
        for a in det.allergens_avoid:
            if a not in session_allergens:
                session_allergens.append(a)
        for d in det.dietary_tags:
            if d not in session_dietary:
                session_dietary.append(d)
        if det.kitchen_note and not note:
            note = det.kitchen_note

    for a in persisted_allergens:
        if a not in session_allergens:
            session_allergens.append(a)
    for d in persisted_dietary:
        if d not in session_dietary:
            session_dietary.append(d)

    if session_allergens:
        session.context["allergen_avoid"] = session_allergens
    if session_dietary:
        session.context["dietary_tags"] = session_dietary
    if note:
        session.context["kitchen_allergy_note"] = note


# --------------------------------------------------------------------------- #
# Tag-enriched menu search
# --------------------------------------------------------------------------- #


def _format_tag_list(tags: list[str]) -> str:
    return ",".join(tags) if tags else "—"


def _item_to_tagged_line(item: RestaurantMenuItem, lang: str, *, uncertain: bool = False) -> str:
    name = localized_name(item, lang)
    price = format_shekel(int(item.price_agorot or 0))
    allergens = parse_json_tags(item.allergen_tags_json, ALLERGEN_TAGS)
    dietary = parse_json_tags(item.dietary_tags_json, DIETARY_TAGS)
    recipe = parse_json_tags(item.recipe_tags_json, RECIPE_TAGS)
    protein = parse_json_tags(item.protein_tags_json, PROTEIN_TAGS)
    flag = " (uncertain: true)" if uncertain else ""
    tags_str = (
        f"allergens=[{_format_tag_list(allergens)}] "
        f"dietary=[{_format_tag_list(dietary)}] "
        f"recipe=[{_format_tag_list(recipe)}] "
        f"protein=[{_format_tag_list(protein)}]"
    )
    return f"- {name} | {price} | id={item.id}{flag} | {tags_str}"


def _safety_filter_for_session(session: AgentSession) -> tuple[list[str], list[str]]:
    allergens = [str(a).lower() for a in (session.context.get("allergen_avoid") or []) if a]
    dietary = [str(d).lower() for d in (session.context.get("dietary_tags") or []) if d]
    return allergens, dietary


def search_menu_tagged(
    db: Session,
    *,
    restaurant_id: str,
    customer: CustomerProfile | None,
    session: AgentSession,
    query: str,
    limit: int = 6,
) -> str:
    """Return search results formatted with tags + safety flags for the LLM to reason over."""
    lang = session.language or "ar"
    allergens, dietary = _safety_filter_for_session(session)
    raw_hits = menu_kb.search_menu(
        db,
        restaurant_id,
        query,
        lang,
        customer=customer,
        limit=max(limit * 2, limit),
    )
    if not raw_hits:
        return "No matching items found." if lang == "en" else "ما لقيت أصناف تطابق هذا الطلب."

    items: list[RestaurantMenuItem] = []
    for row in raw_hits:
        item = db.get(RestaurantMenuItem, row.get("id"))
        if item is not None and not item.is_deleted and item.is_available:
            items.append(item)

    safe, uncertain = MenuSafetyFilter.filter_items(
        items,
        allergen_avoid=allergens,
        dietary_required=dietary,
        strict=get_settings().abuu_allergen_strict_mode,
    )

    suggestions_index: list[dict[str, Any]] = []
    lines: list[str] = []
    shown = 0
    for item in safe:
        lines.append(_item_to_tagged_line(item, lang, uncertain=False))
        suggestions_index.append({"idx": shown + 1, "menu_item_id": item.id})
        shown += 1
        if shown >= limit:
            break
    if shown < limit and uncertain:
        for item in uncertain:
            lines.append(_item_to_tagged_line(item, lang, uncertain=True))
            suggestions_index.append({"idx": shown + 1, "menu_item_id": item.id})
            shown += 1
            if shown >= limit:
                break

    if not lines:
        msg = (
            "All matches were filtered out by the customer's known allergies. "
            "Suggest a different category or ask the customer."
            if lang == "en"
            else "كل النتائج مستثناة بسبب الحساسية المعروفة. اقترح صنف مختلف أو اسأل العميل."
        )
        return msg

    session.context["suggested_items"] = suggestions_index
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# SmartWaiterSkills — tool dispatcher
# --------------------------------------------------------------------------- #


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


def _require_restaurant(session: AgentSession, lang: str) -> str:
    if not session.restaurant_id:
        msg = "اختر مطعم أول. استعمل list_restaurants ثم select_restaurant." if lang == "ar" else (
            "Select a restaurant first. Call list_restaurants then select_restaurant."
        )
        raise ValueError(msg)
    return session.restaurant_id


def _cart_text(session: AgentSession, order: CustomerOrder | None) -> str:
    lang = session.language or "ar"
    if order is None or not session.cart:
        return "السلة فارغة." if lang == "ar" else "Cart is empty."
    lines: list[str] = []
    for row in session.cart:
        price = format_shekel(int(float(row.get("price", 0)) * 100))
        lines.append(f"- {row.get('name', '')} x{row.get('quantity', 1)} ({price})")
    total = format_shekel(int(order.total_agorot or 0))
    header = "السلة:" if lang == "ar" else "Cart:"
    total_label = "المجموع" if lang == "ar" else "Total"
    return f"{header}\n" + "\n".join(lines) + f"\n{total_label}: {total}"


class SmartWaiterSkills:
    def __init__(self, db: Session, session: AgentSession, *, customer: CustomerProfile) -> None:
        self.db = db
        self.session = session
        self.customer = customer
        self.lang = session.language or "ar"

    # -------------------- dispatch -------------------- #

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            return f"Unknown tool: {tool_name}"
        try:
            return handler(tool_input or {})
        except ValueError as exc:
            return str(exc)
        except Exception:
            logger.exception(
                "smart_agent_tool_failed tool=%s phone=%s restaurant=%s",
                tool_name,
                self.session.customer_wa_number,
                self.session.restaurant_id,
            )
            return (
                "حصل خطأ أثناء تنفيذ الإجراء، حاول مرة ثانية."
                if self.lang == "ar"
                else "Something went wrong with that action. Please try again."
            )

    # -------------------- menu / search -------------------- #

    def _tool_search_menu(self, inp: dict[str, Any]) -> str:
        restaurant_id = _require_restaurant(self.session, self.lang)
        query = str(inp.get("query") or "").strip()
        limit = int(inp.get("limit") or 6)
        return search_menu_tagged(
            self.db,
            restaurant_id=restaurant_id,
            customer=self.customer,
            session=self.session,
            query=query,
            limit=max(1, min(limit, 10)),
        )

    # -------------------- cart -------------------- #

    def _tool_add_to_cart(self, inp: dict[str, Any]) -> str:
        restaurant_id = _require_restaurant(self.session, self.lang)
        items_arg = inp.get("items")

        # Backwards-compatible: also accept legacy single-item shape {item_id, quantity, notes}.
        if not isinstance(items_arg, list) and inp.get("item_id"):
            items_arg = [
                {
                    "item_id": inp.get("item_id"),
                    "quantity": inp.get("quantity") or 1,
                    "notes": inp.get("notes") or "",
                }
            ]
        if not isinstance(items_arg, list) or not items_arg:
            raise ValueError("items array is required")

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

        added_names: list[str] = []
        last_item: RestaurantMenuItem | None = None
        for entry in items_arg:
            if not isinstance(entry, dict):
                continue
            item_id = str(entry.get("item_id") or "").strip()
            quantity = max(1, int(entry.get("quantity") or 1))
            notes = str(entry.get("notes") or "").strip()
            item = self.db.get(RestaurantMenuItem, item_id) if item_id else None
            if item is None or item.is_deleted or not item.is_available:
                raise ValueError(f"Item not found or unavailable: {item_id}")
            AbuuOrderDraftService.add_item(self.db, order, item, quantity=quantity)
            if notes:
                existing = order.notes or ""
                line_note = f"{localized_name(item, self.lang)}: {notes}"
                order.notes = f"{existing}\n{line_note}".strip() if existing else line_note
                self.db.add(order)
            added_names.append(f"{quantity}× {localized_name(item, self.lang)}")
            last_item = item

        fingerprint = AbuuOrderDraftService.cart_fingerprint(self.db, order)
        self.session.context = AbuuOrderDraftService.mark_cart_changed(self.session.context, fingerprint)
        _refresh_cart(self.db, self.session, order)

        addon_hint = ""
        if last_item is not None:
            hint, self.session.context = suggest_addons(
                self.db,
                restaurant_id=restaurant_id,
                main_item=last_item,
                active_categories=self.session.context.get("active_categories") or [],
                context=self.session.context,
                lang=self.lang,
            )
            addon_hint = hint or ""

        summary = self._tool_get_cart({})
        added_label = "تمت إضافة" if self.lang == "ar" else "Added"
        summary = f"{added_label}: {', '.join(added_names)}\n{summary}"
        if addon_hint:
            suggestion_label = "اقتراح" if self.lang == "ar" else "Suggestion"
            summary += f"\n\n{suggestion_label}: {addon_hint}"
        return summary

    def _tool_remove_from_cart(self, inp: dict[str, Any]) -> str:
        order = _get_draft_order(self.db, self.session)
        if order is None:
            raise ValueError("Cart is empty")
        AbuuOrderDraftService.remove_item(self.db, order, item_id=str(inp.get("item_id") or ""))
        _refresh_cart(self.db, self.session, order)
        return self._tool_get_cart({})

    def _tool_get_cart(self, _inp: dict[str, Any]) -> str:
        order = _get_draft_order(self.db, self.session)
        return _cart_text(self.session, order)

    # -------------------- allergies -------------------- #

    def _tool_set_allergy(self, inp: dict[str, Any]) -> str:
        allergens_raw = inp.get("allergens") if isinstance(inp.get("allergens"), list) else []
        dietary_raw = inp.get("dietary") if isinstance(inp.get("dietary"), list) else []
        note = str(inp.get("note") or "").strip()

        allergens = [str(a).strip().lower() for a in allergens_raw if str(a).strip().lower() in ALLERGEN_TAGS]
        dietary = [str(d).strip().lower() for d in dietary_raw if str(d).strip().lower() in DIETARY_TAGS]

        if not allergens and not dietary and not note:
            return (
                "لم يتم إدخال حساسية. حدد allergens أو dietary."
                if self.lang == "ar"
                else "No allergy info captured. Please pass allergens or dietary."
            )

        session_allergens = list(self.session.context.get("allergen_avoid") or [])
        session_dietary = list(self.session.context.get("dietary_tags") or [])
        for a in allergens:
            if a not in session_allergens:
                session_allergens.append(a)
        for d in dietary:
            if d not in session_dietary:
                session_dietary.append(d)
        if session_allergens:
            self.session.context["allergen_avoid"] = session_allergens
        if session_dietary:
            self.session.context["dietary_tags"] = session_dietary
        if note:
            self.session.context["kitchen_allergy_note"] = note[:512]
        elif allergens or dietary:
            auto_note = ", ".join(allergens + dietary)
            self.session.context["kitchen_allergy_note"] = (
                self.session.context.get("kitchen_allergy_note") or f"Allergy/Diet: {auto_note}"
            )

        _persist_customer_safety(self.db, self.customer, allergens=allergens, dietary=dietary)

        bits = []
        if allergens:
            bits.append(("حساسية: " if self.lang == "ar" else "Allergies: ") + ", ".join(allergens))
        if dietary:
            bits.append(("نظام: " if self.lang == "ar" else "Diet: ") + ", ".join(dietary))
        saved = " | ".join(bits) if bits else "ok"
        if self.lang == "ar":
            return f"تم حفظ ({saved}). راح أراعيها في كل اقتراحاتي وفي المرات القادمة."
        return f"Saved ({saved}). I'll honour this every time you order."

    # -------------------- confirm (single source of truth) -------------------- #

    def _tool_confirm_order(self, _inp: dict[str, Any]) -> str:
        order = _get_draft_order(self.db, self.session)
        if order is None:
            raise ValueError("Cart is empty" if self.lang == "en" else "السلة فارغة.")
        if order.total_agorot <= 0:
            raise ValueError("Cart is empty" if self.lang == "en" else "السلة فارغة.")

        fingerprint = AbuuOrderDraftService.cart_fingerprint(self.db, order)
        if self.session.context.get("confirmed_cart_fingerprint") == fingerprint:
            return confirm_pending_payment_message(order, self.lang)

        if not order.delivery_address_id:
            addr = get_default_address(self.db, self.customer.id)
            if addr is None:
                if self.lang == "ar":
                    return "ابعت دبوس موقع واتساب (📍 Location) قبل التأكيد علشان نوصلك."
                return "Please send a WhatsApp location pin (📍 Location) before confirming so we can deliver."
            order.delivery_address_id = addr.id
            order.location_missing = False
            self.db.add(order)

        allergy_note = self.session.context.get("kitchen_allergy_note") or None
        AbuuOrderDraftService.confirm_draft(self.db, order, allergy_note=allergy_note)
        self.session.context["confirmed_cart_fingerprint"] = fingerprint
        self.session.stage = "done"

        # Single source of truth: confirm + (auto-send) + webhook. mark_paid_manual is idempotent
        # (begin_event keyed on f"order:{order.id}:paid"), so we never double-fire here.
        order_sent = False
        if get_settings().yallasay_auto_send_on_confirm:
            try:
                # mark_paid_manual is idempotent (idem key f"order:{id}:paid") and itself
                # calls AbuuNotificationService.notify_order_paid -> no double-send.
                AbuuOrderService.mark_paid_manual(self.db, order, confirmed_by="smart_agent_whatsapp")
                order_sent = True
            except ValueError:
                logger.warning("smart_agent_mark_paid_skipped order_id=%s status=%s", order.id, order.status)

        # Optional outbound restaurant webhook (best-effort, 5s timeout).
        try:
            post_restaurant_webhook(order)
        except Exception:
            logger.exception("smart_agent_webhook_failed order_id=%s", order.id)

        # If auto-send was off, still notify the restaurant portal so they can act on the confirmed
        # (pending-payment) order. The UNIQUE (order_id, kind, target_type, target_id) constraint
        # on abuu_notifications guarantees no duplicate notification even if both paths ran.
        if not order_sent:
            try:
                AbuuNotificationService.notify_order_paid(self.db, order)
            except Exception:
                logger.exception("smart_agent_notify_failed order_id=%s", order.id)

        from app.abuu.agent.session import clear_session

        order_id = order.id
        clear_session(self.db, self.session.customer_wa_number)
        self.session.active_order_id = order_id

        if order_sent:
            msg = order_sent_to_restaurant_message(order, self.lang)
        else:
            msg = confirm_pending_payment_message(order, self.lang)

        settings = resolve_settings(self.db, restaurant_id=order.restaurant_id)
        prep = settings.prep_minutes
        if prep:
            if self.lang == "ar":
                msg += f"\nالوقت المتوقع: ~{prep} دقيقة."
            else:
                msg += f"\nEstimated prep time: ~{prep} minutes."

        return msg

    # -------------------- restaurants -------------------- #

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
        ranked = rank_restaurants(self.db, lat=lat, lng=lng, categories=categories, limit=15)
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
            raise ValueError("Restaurant not found" if self.lang == "en" else "ما لقيت المطعم.")
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
            return f"تم اختيار {name}. شو حابب تأكل؟ قول لي وأنا أقترح."
        return f"Selected {name}. What would you like? I'll suggest."

    def _tool_change_restaurant(self, _inp: dict[str, Any]) -> str:
        clear_restaurant_binding(self.db, self.session)
        self.session.cart = []
        return self._tool_list_restaurants({})

    # -------------------- offers / policy / misc -------------------- #

    def _tool_list_offers(self, inp: dict[str, Any]) -> str:
        prefetched = self.session.context.get("prefetched_offers")
        if isinstance(prefetched, str) and prefetched.strip():
            self.session.context.pop("prefetched_offers", None)
            return prefetched
        query = str(inp.get("query") or "").strip()
        categories = categories_from_offer_query(query) if query else None
        offers = AbuuOfferService.list_active(
            self.db,
            restaurant_id=self.session.restaurant_id,
            categories=categories,
            limit=15,
        )
        return format_offers_list(self.db, offers, lang=self.lang)

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
                return "تم إلغاء الطلب. قول 'يلا ساي' لما تكون جاهز للبدء من جديد."
            return "Order cancelled. Say 'yallasay' anytime to start again."
        return "ما في طلب نشط لإلغائه." if self.lang == "ar" else "No active order to cancel."

    def _tool_escalate_to_admin(self, inp: dict[str, Any]) -> str:
        settings = resolve_settings(self.db, restaurant_id=self.session.restaurant_id)
        reason = str(inp.get("reason") or "").strip()
        base = settings.escalation_rules_ar if self.lang == "ar" else settings.escalation_rules_en
        if reason:
            return f"{base or ''}\n({reason})".strip()
        return base or kb_fallback_message(self.lang)

    def _tool_save_customer_name(self, inp: dict[str, Any]) -> str:
        name = str(inp.get("name") or "").strip()
        if not name:
            raise ValueError("Name is required")
        save_customer_name(self.customer, name)
        self.db.add(self.customer)
        if self.lang == "ar":
            return f"تشرفنا {name.split()[0]}!"
        return f"Nice to meet you, {name.split()[0]}!"

    def _tool_track_order(self, inp: dict[str, Any]) -> str:
        order_id = str(inp.get("order_id") or self.session.active_order_id or "").strip()
        if not order_id:
            row = self.db.execute(
                select(CustomerOrder)
                .where(CustomerOrder.customer_id == self.customer.id)
                .order_by(CustomerOrder.created_at.desc())
            ).scalars().first()
            if row is None:
                raise ValueError("No order found" if self.lang == "en" else "ما في طلب.")
            order_id = row.id
        order = self.db.get(CustomerOrder, order_id)
        if order is None:
            raise ValueError("Order not found" if self.lang == "en" else "ما لقيت الطلب.")
        assignment = self.db.execute(
            select(DeliveryAssignment).where(DeliveryAssignment.order_id == order.id)
        ).scalar_one_or_none()
        return order_status_message(order, assignment, self.lang)


def execute_tool(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    tool_name: str,
    tool_input: dict[str, Any] | str,
) -> str:
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except json.JSONDecodeError:
            tool_input = {}
    skills = SmartWaiterSkills(db, session, customer=customer)
    return skills.execute(tool_name, tool_input or {})
