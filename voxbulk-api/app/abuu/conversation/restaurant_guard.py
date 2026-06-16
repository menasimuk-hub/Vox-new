"""One cart = one restaurant. Block silent cross-restaurant mixing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerOrder, CustomerProfile, Restaurant, RestaurantMenuItem
from app.abuu.services.kb_service import resolve_settings
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import format_shekel, localized_name

ORDER_FEE_NIS = 15
ORDER_FEE_AGOROT = 1500


class RestaurantMismatchError(Exception):
    def __init__(self, *, bound_id: str, target_id: str, target_name: str) -> None:
        self.bound_id = bound_id
        self.target_id = target_id
        self.target_name = target_name
        super().__init__(f"cross_restaurant:{bound_id}->{target_id}")


@dataclass
class GuardResult:
    ok: bool
    action: str
    order: CustomerOrder | None = None
    item: RestaurantMenuItem | None = None
    bound_restaurant_id: str | None = None
    conflict: dict[str, Any] | None = None
    message_key: str | None = None


def delivery_fee_agorot(db: Session, restaurant_id: str | None) -> int:
    settings = resolve_settings(db, restaurant_id=restaurant_id)
    fee = int(settings.delivery_fee_agorot or ORDER_FEE_AGOROT)
    return fee if fee > 0 else ORDER_FEE_AGOROT


def bound_restaurant_id(order: CustomerOrder | None, context: dict) -> str | None:
    if order and order.restaurant_id and order.status == "draft":
        lines = order.total_agorot or 0
        if lines > 0 or context.get("restaurant_selected"):
            return str(order.restaurant_id)
    rid = str(context.get("restaurant_id") or "").strip()
    return rid or None


def clear_cart_for_switch(db: Session, order: CustomerOrder) -> None:
    from sqlalchemy import delete

    from app.abuu.models.entities import CustomerOrderItem

    db.execute(delete(CustomerOrderItem).where(CustomerOrderItem.order_id == order.id))
    order.total_agorot = 0
    db.add(order)
    db.flush()


def switch_restaurant_order(
    db: Session,
    *,
    customer: CustomerProfile,
    order: CustomerOrder | None,
    restaurant: Restaurant,
) -> CustomerOrder:
    if order is not None and order.status == "draft":
        clear_cart_for_switch(db, order)
        order.restaurant_id = restaurant.id
        db.add(order)
        db.flush()
        return order
    return AbuuOrderDraftService.start_draft(db, customer=customer, restaurant=restaurant)


def clear_switch_context(context: dict) -> dict:
    """Remove stale cart/switch state after restaurant change."""
    ctx = dict(context)
    for key in (
        "pending_restaurant_switch",
        "suggested_items",
        "last_food_search",
        "confirmed_cart_fingerprint",
        "cart_fingerprint",
        "pending_confirm_fingerprint",
        "last_addon_suggestions",
        "pending_addon_items",
        "cart_item_ids",
        "last_main_item_type",
    ):
        ctx.pop(key, None)
    return ctx


def order_is_bound(order: CustomerOrder | None, context: dict) -> bool:
    if order is None or order.status != "draft":
        return False
    if int(order.total_agorot or 0) > 0:
        return True
    return bool(context.get("restaurant_selected") and order.restaurant_id)


def bind_restaurant_context(context: dict, restaurant_id: str) -> dict:
    ctx = dict(context)
    ctx["restaurant_id"] = restaurant_id
    ctx["restaurant_selected"] = True
    return ctx


def cross_restaurant_message(
    db: Session,
    *,
    lang: str,
    current_restaurant: Restaurant,
    target_restaurant: Restaurant,
    target_item_name: str,
) -> str:
    current_name = localized_name(current_restaurant, lang)
    target_name = localized_name(target_restaurant, lang)
    fee = delivery_fee_agorot(db, current_restaurant.id) / 100
    if lang == "en":
        return (
            f"That item ({target_item_name}) is from **{target_name}** — your cart is with **{current_name}**.\n"
            f"We do one order per restaurant. Each order has a {fee:.0f} ₪ fee, "
            f"so two restaurants means two separate orders.\n"
            "Reply **switch** to change restaurant (cart clears), or **keep** to stay with your current order."
        )
    return (
        f"هاد الصنف ({target_item_name}) من **{target_name}** — طلبك الحالي من **{current_name}** 🍽️\n"
        f"كل طلب لمطعم واحد فقط. رسوم كل طلب {fee:.0f} ₪ — "
        f"مطعمين = طلبين منفصلين ({fee * 2:.0f} ₪ رسوم).\n"
        "اكتب **غيّر** للتبديل (السلة تفرّغ)، أو **خلي** لإبقاء طلبك الحالي."
    )


class RestaurantGuard:
    @staticmethod
    def try_add_item(
        db: Session,
        *,
        customer: CustomerProfile,
        order: CustomerOrder | None,
        context: dict,
        item: RestaurantMenuItem,
        restaurant: Restaurant,
        lang: str,
        allow_switch: bool = False,
    ) -> GuardResult:
        target_rid = restaurant.id
        bound = bound_restaurant_id(order, context)

        if bound and bound != target_rid and not allow_switch:
            current = db.get(Restaurant, bound)
            if current is None:
                current = restaurant
            return GuardResult(
                ok=False,
                action="cross_restaurant_blocked",
                conflict={
                    "from_restaurant_id": bound,
                    "to_restaurant_id": target_rid,
                    "item_id": item.id,
                    "item_name": localized_name(item, lang),
                },
                message_key="cross_restaurant",
            )

        if bound and bound != target_rid and allow_switch and order is not None:
            order = switch_restaurant_order(db, customer=customer, order=order, restaurant=restaurant)
        elif order is None or order.restaurant_id != target_rid:
            order = AbuuOrderDraftService.start_draft(db, customer=customer, restaurant=restaurant)
        elif order.restaurant_id != target_rid:
            return GuardResult(
                ok=False,
                action="cross_restaurant_blocked",
                conflict={"from_restaurant_id": order.restaurant_id, "to_restaurant_id": target_rid},
            )

        order = AbuuOrderDraftService.add_item(db, order, item)
        context = dict(context)
        context["restaurant_id"] = target_rid
        context["restaurant_selected"] = True
        context.pop("pending_restaurant_switch", None)

        return GuardResult(
            ok=True,
            action="item_added",
            order=order,
            item=item,
            bound_restaurant_id=target_rid,
        )
