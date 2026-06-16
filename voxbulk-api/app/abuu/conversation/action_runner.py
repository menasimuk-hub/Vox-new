"""Execute cart and restaurant actions (deterministic backend)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession, save_session
from app.abuu.conversation.fact_bundle import FactBundle, FoodItemFact
from app.abuu.conversation.intent_router import AbuuIntent
from app.abuu.conversation.restaurant_guard import (
    RestaurantGuard,
    bound_restaurant_id,
    cross_restaurant_message,
    switch_restaurant_order,
)
from app.abuu.models.entities import CustomerOrder, CustomerProfile, Restaurant, RestaurantMenuItem
from app.abuu.services.addon_suggestion_service import suggest_addons
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import format_shekel, item_added_message, localized_name


@dataclass
class ActionResult:
    action: str
    order: CustomerOrder | None = None
    reply_hint: str | None = None
    upsell_hint: str | None = None
    delegate: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ActionRunner:
    @staticmethod
    def run(
        db: Session,
        intent: AbuuIntent,
        facts: FactBundle,
        session: AgentSession,
        *,
        customer: CustomerProfile,
        order: CustomerOrder | None,
    ) -> ActionResult:
        ctx = dict(session.context or {})

        if intent.name == "restaurant_switch_confirm":
            pending = ctx.get("pending_restaurant_switch") or {}
            item_id = pending.get("item_id")
            rest_id = pending.get("to_restaurant_id")
            if not item_id or not rest_id:
                return ActionResult(action="noop")
            item = db.get(RestaurantMenuItem, item_id)
            restaurant = db.get(Restaurant, rest_id)
            if item is None or restaurant is None:
                ctx.pop("pending_restaurant_switch", None)
                session.context = ctx
                return ActionResult(action="noop")
            guard = RestaurantGuard.try_add_item(
                db,
                customer=customer,
                order=order,
                context=ctx,
                item=item,
                restaurant=restaurant,
                lang=session.language or "ar",
                allow_switch=True,
            )
            if guard.ok and guard.order and guard.item:
                session.restaurant_id = guard.bound_restaurant_id
                session.active_order_id = guard.order.id
                session.cart = ActionRunner._reload_cart(db, guard.order)
                ctx.update({"restaurant_id": guard.bound_restaurant_id, "restaurant_selected": True})
                session.context = ctx
                addon_msg, ctx = suggest_addons(
                    db,
                    restaurant_id=guard.bound_restaurant_id or "",
                    main_item=guard.item,
                    active_categories=intent.categories,
                    context=ctx,
                    lang=session.language or "ar",
                )
                session.context = ctx
                return ActionResult(
                    action="item_added",
                    order=guard.order,
                    reply_hint=item_added_message(guard.item, guard.order, session.language or "ar", addon_hint=addon_msg),
                )
            return ActionResult(action="noop")

        if intent.name == "restaurant_switch_keep":
            ctx.pop("pending_restaurant_switch", None)
            session.context = ctx
            lang = session.language or "ar"
            hint = "تمام، بكمّل على طلبك الحالي 👍" if lang == "ar" else "OK, keeping your current order 👍"
            return ActionResult(action="switch_dismissed", reply_hint=hint)

        if intent.name == "confirm":
            return ActionResult(action="confirm", delegate="confirm")

        if intent.name == "cancel":
            if order:
                AbuuOrderDraftService.cancel_draft(db, order)
            return ActionResult(action="cancelled", delegate="cancel")

        if intent.name in {"select_item", "cart_modify"} and facts.internal_index.get("pick"):
            pick = facts.internal_index["pick"]
            item = db.get(RestaurantMenuItem, pick["menu_item_id"])
            restaurant = db.get(Restaurant, pick["restaurant_id"])
            if item and restaurant:
                return ActionRunner._add_item(
                    db, session, customer, order, item, restaurant, intent.categories
                )

        if intent.name == "select_item" and len(facts.food_items) == 1:
            f = facts.food_items[0]
            item = db.get(RestaurantMenuItem, f.menu_item_id)
            restaurant = db.get(Restaurant, f.restaurant_id)
            if item and restaurant:
                return ActionRunner._add_item(
                    db, session, customer, order, item, restaurant, intent.categories
                )

        return ActionResult(action="none")

    @staticmethod
    def _add_item(
        db: Session,
        session: AgentSession,
        customer: CustomerProfile,
        order: CustomerOrder | None,
        item: RestaurantMenuItem,
        restaurant: Restaurant,
        categories: list[str],
    ) -> ActionResult:
        lang = session.language or "ar"
        ctx = dict(session.context or {})
        guard = RestaurantGuard.try_add_item(
            db,
            customer=customer,
            order=order,
            context=ctx,
            item=item,
            restaurant=restaurant,
            lang=lang,
        )
        if not guard.ok and guard.action == "cross_restaurant_blocked":
            conflict = guard.conflict or {}
            from_id = conflict.get("from_restaurant_id")
            to_id = conflict.get("to_restaurant_id")
            current = db.get(Restaurant, from_id) if from_id else None
            target = db.get(Restaurant, to_id) if to_id else restaurant
            if current and target:
                ctx["pending_restaurant_switch"] = {
                    "from_restaurant_id": from_id,
                    "to_restaurant_id": to_id,
                    "item_id": item.id,
                    "item_name": conflict.get("item_name") or localized_name(item, lang),
                }
                session.context = ctx
                return ActionResult(
                    action="cross_restaurant_blocked",
                    reply_hint=cross_restaurant_message(
                        db,
                        lang=lang,
                        current_restaurant=current,
                        target_restaurant=target,
                        target_item_name=conflict.get("item_name") or localized_name(item, lang),
                    ),
                )

        if guard.ok and guard.order and guard.item:
            session.restaurant_id = guard.bound_restaurant_id
            session.active_order_id = guard.order.id
            session.cart = ActionRunner._reload_cart(db, guard.order)
            ctx["restaurant_id"] = guard.bound_restaurant_id
            ctx["restaurant_selected"] = True
            addon_msg, ctx = suggest_addons(
                db,
                restaurant_id=guard.bound_restaurant_id or "",
                main_item=guard.item,
                active_categories=categories,
                context=ctx,
                lang=lang,
            )
            session.context = ctx
            return ActionResult(
                action="item_added",
                order=guard.order,
                reply_hint=item_added_message(guard.item, guard.order, lang, addon_hint=addon_msg),
                upsell_hint=addon_msg,
            )
        return ActionResult(action="item_not_found")

    @staticmethod
    def _reload_cart(db: Session, order: CustomerOrder) -> list[dict]:
        from app.abuu.agent.session import _cart_from_order

        return _cart_from_order(db, order)
