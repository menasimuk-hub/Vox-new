"""Skill router for Abuu WhatsApp agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerOrder, DeliveryAssignment, Restaurant, RestaurantMenuItem
from app.abuu.services.addon_suggestion_service import suggest_addons
from app.abuu.services.agent_settings_service import is_skill_enabled
from app.abuu.services.conversation_ai_service import SkillClassification
from app.abuu.services.customer_memory_service import (
    apply_saved_address_to_order,
    first_name,
    remember_preference,
    save_customer_name,
    saved_address_summary,
)
from app.abuu.conversation.fact_bundle import FactBundleLoader
from app.abuu.conversation.intent_router import AbuuIntent
from app.abuu.conversation.restaurant_guard import RestaurantGuard, RestaurantMismatchError, cross_restaurant_message
from app.abuu.services.kb_service import answer_kb_question, format_greeting, kb_fallback_message, resolve_settings
from app.abuu.services.location_service import attach_default_address_if_present, get_default_address
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.restaurant_discovery_service import (
    format_restaurant_list,
    pick_restaurant_by_ref,
    rank_restaurants,
)
from app.abuu.services.skill_definitions import (
    SKILL_ANSWER_KB,
    SKILL_BUILD_CART,
    SKILL_CANCEL_OR_REFUND,
    SKILL_CAPTURE_LOCATION,
    SKILL_CAPTURE_NAME,
    SKILL_CONFIRM_ORDER,
    SKILL_GREET_CUSTOMER,
    SKILL_HANDOFF_TO_ADMIN,
    SKILL_MENU_RECOMMEND,
    SKILL_ORDER_STATUS,
    SKILL_RESTAURANT_SEARCH,
)
from app.abuu.market.registry import get_market_agent, marketplace_scope
from app.abuu.services.yallasay_wa_snapshot_service import YallasayWaSnapshotService
from app.abuu.services.reply_service import (
    ask_name_message,
    category_clarification_message,
    conversational_menu_message,
    item_added_message,
    localized_name,
    order_status_message,
)
from app.core.config import get_settings


@dataclass
class TurnContext:
    abuu_db: Session
    main_db: Session
    phone: str
    text: str
    session: Any
    customer: Any
    lang: str
    message_id: str | None
    org_id: str | None
    classification: SkillClassification
    context: dict = field(default_factory=dict)
    order: CustomerOrder | None = None


@dataclass
class SkillResult:
    skill: str
    ok: bool
    action: str
    next_step: str | None
    reply: str
    context_patch: dict = field(default_factory=dict)
    handled: bool = True
    extra: dict = field(default_factory=dict)


class AbuuSkillRouter:
    @staticmethod
    def dispatch(ctx: TurnContext) -> SkillResult:
        skill = ctx.classification.skill
        if not is_skill_enabled(ctx.abuu_db, skill):
            skill = SKILL_HANDOFF_TO_ADMIN

        handlers: dict[str, Callable[[TurnContext], SkillResult]] = {
            SKILL_GREET_CUSTOMER: AbuuSkillRouter._greet_customer,
            SKILL_CAPTURE_NAME: AbuuSkillRouter._capture_name,
            SKILL_CAPTURE_LOCATION: AbuuSkillRouter._capture_location_delegated,
            SKILL_RESTAURANT_SEARCH: AbuuSkillRouter._restaurant_search,
            SKILL_MENU_RECOMMEND: AbuuSkillRouter._menu_recommend,
            SKILL_BUILD_CART: AbuuSkillRouter._build_cart,
            SKILL_CONFIRM_ORDER: AbuuSkillRouter._confirm_order_delegated,
            SKILL_ANSWER_KB: AbuuSkillRouter._answer_kb,
            SKILL_ORDER_STATUS: AbuuSkillRouter._order_status,
            SKILL_CANCEL_OR_REFUND: AbuuSkillRouter._cancel_or_refund,
            SKILL_HANDOFF_TO_ADMIN: AbuuSkillRouter._handoff_to_admin,
        }
        handler = handlers.get(skill, AbuuSkillRouter._build_cart)
        return handler(ctx)

    @staticmethod
    def _lat_lng(ctx: TurnContext) -> tuple[float | None, float | None]:
        addr = get_default_address(ctx.abuu_db, ctx.customer.id)
        if addr and addr.latitude is not None and addr.longitude is not None:
            return addr.latitude, addr.longitude
        return None, None

    @staticmethod
    def _pilot_restaurant_ids(ctx: TurnContext) -> tuple[str, ...] | None:
        if not get_settings().abuu_pilot_only:
            return None
        return get_market_agent(ctx.abuu_db).pilot_restaurant_ids

    @staticmethod
    def _market_restaurant_list(ctx: TurnContext) -> str | None:
        market = get_market_agent(ctx.abuu_db)
        lang = ctx.lang if ctx.lang in {"ar", "en"} else "ar"
        return YallasayWaSnapshotService.get_body(
            ctx.abuu_db,
            scope=marketplace_scope(market.id),
            kind="restaurant_list",
            lang=lang,
        )

    @staticmethod
    def _append_restaurant_list(ctx: TurnContext, reply: str) -> str:
        listing = AbuuSkillRouter._market_restaurant_list(ctx)
        if listing:
            return f"{reply}\n\n{listing}"
        lat, lng = AbuuSkillRouter._lat_lng(ctx)
        ranked = rank_restaurants(
            ctx.abuu_db,
            lat=lat,
            lng=lng,
            categories=None,
            limit=15,
            restaurant_ids=AbuuSkillRouter._pilot_restaurant_ids(ctx),
        )
        if not ranked:
            return reply
        listing = format_restaurant_list(ranked, lang=ctx.lang, page=0, page_size=max(15, len(ranked)))
        return f"{reply}\n\n{listing}"

    @staticmethod
    def _pick_from_food_search(ctx: TurnContext, item_ref: str) -> SkillResult | None:
        pool = list(ctx.context.get("last_food_search") or [])
        if not pool:
            return None
        q = str(item_ref or "").strip().lower()
        if not q:
            return None
        entry: dict | None = None
        if q.isdigit():
            idx = int(q) - 1
            if 0 <= idx < len(pool):
                entry = pool[idx]
        else:
            for candidate in pool:
                if q in str(candidate.get("name", "")).lower():
                    entry = candidate
                    break
        if entry is None:
            return None
        item = ctx.abuu_db.get(RestaurantMenuItem, entry.get("menu_item_id"))
        restaurant = ctx.abuu_db.get(Restaurant, entry.get("restaurant_id"))
        if item is None or restaurant is None:
            return None
        guard = RestaurantGuard.try_add_item(
            ctx.abuu_db,
            customer=ctx.customer,
            order=ctx.order,
            context=dict(ctx.context),
            item=item,
            restaurant=restaurant,
            lang=ctx.lang,
        )
        if not guard.ok and guard.action == "cross_restaurant_blocked":
            current = ctx.abuu_db.get(Restaurant, guard.conflict.get("from_restaurant_id")) if guard.conflict else None
            if current is None and ctx.order:
                current = ctx.abuu_db.get(Restaurant, ctx.order.restaurant_id)
            if current:
                return SkillResult(
                    skill=SKILL_BUILD_CART,
                    ok=False,
                    action="cross_restaurant_blocked",
                    reply=cross_restaurant_message(
                        ctx.abuu_db,
                        lang=ctx.lang,
                        current_restaurant=current,
                        target_restaurant=restaurant,
                        target_item_name=localized_name(item, ctx.lang),
                    ),
                )
            return None
        if not guard.ok or guard.order is None or guard.item is None:
            return None
        order = guard.order
        context = dict(ctx.context)
        context["restaurant_id"] = guard.bound_restaurant_id
        context["restaurant_selected"] = True
        fingerprint = AbuuOrderDraftService.cart_fingerprint(ctx.abuu_db, order)
        context = AbuuOrderDraftService.mark_cart_changed(context, fingerprint)
        addon_msg, context = suggest_addons(
            ctx.abuu_db,
            restaurant_id=guard.bound_restaurant_id or "",
            main_item=guard.item,
            active_categories=context.get("active_categories") or [],
            context=context,
            lang=ctx.lang,
        )
        AbuuOrderDraftService.upsert_session(
            ctx.abuu_db,
            phone=ctx.phone,
            step="browsing",
            context=context,
            active_order_id=order.id,
            message_id=ctx.message_id,
        )
        return SkillResult(
            skill=SKILL_BUILD_CART,
            ok=True,
            action="item_added",
            next_step="browsing",
            reply=item_added_message(guard.item, order, ctx.lang, addon_hint=addon_msg),
            context_patch=context,
            extra={"order_id": order.id},
        )

    @staticmethod
    def _greet_customer(ctx: TurnContext) -> SkillResult:
        lat, lng = AbuuSkillRouter._lat_lng(ctx)
        settings = resolve_settings(ctx.abuu_db)
        context = {
            "restaurant_id": None,
            "greeting_sent": False,
            "active_categories": [],
            "suggested_items": [],
            "restaurant_candidates": [],
            "restaurant_page": 0,
            "ranked_restaurants": [],
        }
        if not ctx.customer.name:
            AbuuOrderDraftService.upsert_session(
                ctx.abuu_db,
                phone=ctx.phone,
                step="awaiting_name",
                context=context,
                active_order_id=None,
                message_id=ctx.message_id,
            )
            return SkillResult(
                skill=SKILL_GREET_CUSTOMER,
                ok=True,
                action="started",
                next_step="awaiting_name",
                reply=ask_name_message(ctx.lang),
                context_patch=context,
            )

        context["greeting_sent"] = True
        AbuuOrderDraftService.upsert_session(
            ctx.abuu_db,
            phone=ctx.phone,
            step="awaiting_preference",
            context=context,
            active_order_id=None,
            message_id=ctx.message_id,
        )
        reply = format_greeting(
            settings,
            first_name=first_name(ctx.customer.name),
            lang=ctx.lang,
            saved_address=saved_address_summary(ctx.abuu_db, ctx.customer),
        )
        if ctx.lang == "ar":
            reply += "\n\nاحكيلي شو جوعان — دجاج، سمك، لحم… وأنا بجهّزلك 👨‍🍳"
        else:
            reply += "\n\nTell me what you're craving — chicken, fish, meat… 👨‍🍳"
        return SkillResult(
            skill=SKILL_GREET_CUSTOMER,
            ok=True,
            action="started",
            next_step="awaiting_preference",
            reply=reply,
            context_patch=context,
        )

    @staticmethod
    def _capture_name(ctx: TurnContext) -> SkillResult:
        name = ctx.classification.item_query or ctx.text
        save_customer_name(ctx.customer, name)
        ctx.abuu_db.add(ctx.customer)
        context = dict(ctx.context)
        context["greeting_sent"] = True
        settings = resolve_settings(ctx.abuu_db)
        AbuuOrderDraftService.upsert_session(
            ctx.abuu_db,
            phone=ctx.phone,
            step="awaiting_preference",
            context=context,
            active_order_id=ctx.session.active_order_id if ctx.session else None,
            message_id=ctx.message_id,
        )
        reply = format_greeting(
            settings,
            first_name=first_name(ctx.customer.name),
            lang=ctx.lang,
            saved_address=saved_address_summary(ctx.abuu_db, ctx.customer),
        )
        if ctx.lang == "ar":
            reply += "\n\nاحكيلي شو جوعان — دجاج، سمك، لحم… وأنا بجهّزلك 👨‍🍳"
        else:
            reply += "\n\nTell me what you're craving — chicken, fish, meat… 👨‍🍳"
        return SkillResult(
            skill=SKILL_CAPTURE_NAME,
            ok=True,
            action="name_saved",
            next_step="awaiting_preference",
            reply=reply,
            context_patch=context,
        )

    @staticmethod
    def _restaurant_search(ctx: TurnContext) -> SkillResult:
        lat, lng = AbuuSkillRouter._lat_lng(ctx)
        categories = ctx.context.get("active_categories") or ctx.classification.categories
        page = int(ctx.context.get("restaurant_page") or 0)
        if is_show_more_message(ctx.text):
            page += 1
        ranked = rank_restaurants(
            ctx.abuu_db,
            lat=lat,
            lng=lng,
            categories=categories or None,
            limit=15,
            restaurant_ids=AbuuSkillRouter._pilot_restaurant_ids(ctx),
        )
        context = dict(ctx.context)
        context["restaurant_page"] = page
        context["ranked_restaurants"] = [
            {"id": r.restaurant.id, "name_en": r.restaurant.name_en, "name_ar": r.restaurant.name_ar}
            for r in ranked
        ]
        ref = ctx.classification.restaurant_ref or ctx.text
        picked = pick_restaurant_by_ref(ranked, ref) if ctx.session and ctx.session.step == "choosing_restaurant" else None
        if picked is None and ctx.classification.restaurant_ref:
            picked = pick_restaurant_by_ref(ranked, ctx.classification.restaurant_ref)
        if picked is not None and not is_show_more_message(ctx.text) and not any(
            w in ctx.text.lower() for w in ("restaurant", "مطاعم", "nearby", "list")
        ):
            try:
                order = AbuuOrderDraftService.ensure_order(
                    ctx.abuu_db,
                    customer=ctx.customer,
                    restaurant=picked,
                    existing_order=ctx.order,
                )
            except RestaurantMismatchError:
                current = ctx.abuu_db.get(Restaurant, ctx.order.restaurant_id) if ctx.order else None
                if current is None:
                    current = picked
                return SkillResult(
                    skill=SKILL_RESTAURANT_SEARCH,
                    ok=False,
                    action="cross_restaurant_blocked",
                    reply=cross_restaurant_message(
                        ctx.abuu_db,
                        lang=ctx.lang,
                        current_restaurant=current,
                        target_restaurant=picked,
                        target_item_name=localized_name(picked, ctx.lang),
                    ),
                )
            apply_saved_address_to_order(ctx.abuu_db, order, ctx.customer)
            context["restaurant_id"] = picked.id
            AbuuOrderDraftService.upsert_session(
                ctx.abuu_db,
                phone=ctx.phone,
                step="awaiting_preference",
                context=context,
                active_order_id=order.id,
                message_id=ctx.message_id,
            )
            name = picked.name_en if ctx.lang == "en" else picked.name_ar
            if ctx.lang == "en":
                reply = f"Nice choice — {name}! 😋 What would you like to eat?"
            else:
                reply = f"اختيار حلو — {name}! 😋 شو بدك تاكل؟"
            return SkillResult(
                skill=SKILL_RESTAURANT_SEARCH,
                ok=True,
                action="restaurant_selected",
                next_step="awaiting_preference",
                reply=reply,
                context_patch=context,
                extra={"order_id": order.id},
            )

        reply = format_restaurant_list(ranked, lang=ctx.lang, page=page, page_size=max(15, len(ranked) or 15))
        AbuuOrderDraftService.upsert_session(
            ctx.abuu_db,
            phone=ctx.phone,
            step="choosing_restaurant",
            context=context,
            active_order_id=ctx.session.active_order_id if ctx.session else None,
            message_id=ctx.message_id,
        )
        return SkillResult(
            skill=SKILL_RESTAURANT_SEARCH,
            ok=True,
            action="restaurant_list",
            next_step="choosing_restaurant",
            reply=reply,
            context_patch=context,
        )

    @staticmethod
    def _menu_recommend(ctx: TurnContext) -> SkillResult:
        categories = ctx.classification.categories or []
        if len(categories) > 1:
            context = dict(ctx.context)
            context["pending_categories"] = categories
            AbuuOrderDraftService.upsert_session(
                ctx.abuu_db,
                phone=ctx.phone,
                step="awaiting_preference",
                context=context,
                active_order_id=ctx.session.active_order_id if ctx.session else None,
                message_id=ctx.message_id,
            )
            return SkillResult(
                skill=SKILL_MENU_RECOMMEND,
                ok=True,
                action="category_clarification",
                next_step="awaiting_preference",
                reply=category_clarification_message(categories, ctx.lang),
                context_patch=context,
            )

        pending = list(ctx.context.get("pending_categories") or [])
        if pending:
            overlap = [c for c in categories if c in pending]
            if len(overlap) == 1:
                categories = overlap
            elif len(pending) == 1:
                categories = pending

        if not categories:
            categories = ctx.classification.categories

        bound_restaurant_id = str(
            ctx.context.get("restaurant_id") or (ctx.order.restaurant_id if ctx.order else "") or ""
        ).strip()
        lat, lng = AbuuSkillRouter._lat_lng(ctx)
        if not bound_restaurant_id:
            from app.abuu.agent.session import Session as AgentSession

            agent_session = AgentSession(
                customer_wa_number=ctx.phone,
                restaurant_id=None,
                language=ctx.lang,
                active_order_id=ctx.session.active_order_id if ctx.session else None,
                context=dict(ctx.context),
            )
            food_intent = AbuuIntent("food_search", categories=categories or [])
            bundle = FactBundleLoader.load(
                ctx.abuu_db, food_intent, agent_session, customer=ctx.customer
            )
            if bundle.customer_lines:
                context = dict(ctx.context)
                context["active_categories"] = categories
                context["pending_categories"] = categories
                context["last_food_search"] = agent_session.context.get("last_food_search") or []
                AbuuOrderDraftService.upsert_session(
                    ctx.abuu_db,
                    phone=ctx.phone,
                    step="browsing",
                    context=context,
                    active_order_id=ctx.session.active_order_id if ctx.session else None,
                    message_id=ctx.message_id,
                )
                header = "هذي اقتراحات تناسب طلبك 🍽️" if ctx.lang == "ar" else "Here's what matches 🍽️"
                footer = (
                    "قول اسم الطبق اللي بيعجبك وأنا بضيفه 😋"
                    if ctx.lang == "ar"
                    else "Say the dish name you want and I'll add it 😋"
                )
                reply = header + "\n" + "\n".join(bundle.customer_lines) + "\n" + footer
                return SkillResult(
                    skill=SKILL_MENU_RECOMMEND,
                    ok=True,
                    action="food_search",
                    next_step="browsing",
                    reply=reply,
                    context_patch=context,
                )
            if ctx.lang == "en":
                reply = "No matching dishes right now — try another type or ask for restaurants."
            else:
                reply = "ما لقيت أطباق لهذا الطلب حالياً — جرّب نوع تاني أو اسأل عن المطاعم 🙏"
            return SkillResult(skill=SKILL_MENU_RECOMMEND, ok=False, action="no_match", next_step=None, reply=reply)

        ranked = rank_restaurants(
            ctx.abuu_db,
            lat=lat,
            lng=lng,
            categories=categories,
            limit=15,
            restaurant_ids=AbuuSkillRouter._pilot_restaurant_ids(ctx),
        )
        if not ranked:
            if ctx.lang == "en":
                reply = "No nearby restaurants have items for that preference right now."
            else:
                reply = "لا توجد مطاعم قريبة لهذا الاختيار حالياً."
            return SkillResult(skill=SKILL_MENU_RECOMMEND, ok=False, action="no_match", next_step=None, reply=reply)

        restaurant = ranked[0].restaurant
        if bound_restaurant_id:
            picked = ctx.abuu_db.get(Restaurant, bound_restaurant_id)
            if picked is not None:
                restaurant = picked
        order = AbuuOrderDraftService.ensure_order(
            ctx.abuu_db,
            customer=ctx.customer,
            restaurant=restaurant,
            existing_order=ctx.order,
        )
        apply_saved_address_to_order(ctx.abuu_db, order, ctx.customer)
        for cat in categories:
            remember_preference(ctx.customer, category=cat)
        ctx.abuu_db.add(ctx.customer)

        items = AbuuOrderDraftService.list_menu_items(
            ctx.abuu_db,
            restaurant.id,
            categories=categories,
            customer=ctx.customer,
        )
        indexed = list(enumerate(items, start=1))
        context = dict(ctx.context)
        context["restaurant_id"] = restaurant.id
        context["active_categories"] = categories
        context["suggested_items"] = AbuuOrderDraftService.build_suggestion_index(items)
        context.pop("pending_categories", None)
        context["ranked_restaurants"] = [
            {"id": r.restaurant.id, "name_en": r.restaurant.name_en, "name_ar": r.restaurant.name_ar}
            for r in ranked[:3]
        ]

        AbuuOrderDraftService.upsert_session(
            ctx.abuu_db,
            phone=ctx.phone,
            step="browsing",
            context=context,
            active_order_id=order.id,
            message_id=ctx.message_id,
        )
        reply = conversational_menu_message(restaurant, indexed, categories=categories, lang=ctx.lang)
        if len(ranked) > 1:
            if ctx.lang == "en":
                reply += "\nSay **restaurants** to see other nearby places."
            else:
                reply += "\nاكتب **مطاعم** لرؤية مطاعم أخرى قريبة."
        return SkillResult(
            skill=SKILL_MENU_RECOMMEND,
            ok=True,
            action="preference_menu",
            next_step="browsing",
            reply=reply,
            context_patch=context,
            extra={"order_id": order.id, "categories": categories},
        )

    @staticmethod
    def _build_cart(ctx: TurnContext) -> SkillResult:
        restaurant_id = str(ctx.context.get("restaurant_id") or (ctx.order.restaurant_id if ctx.order else ""))
        item_ref = ctx.classification.item_query or ctx.text
        if not restaurant_id or ctx.order is None:
            picked = AbuuSkillRouter._pick_from_food_search(ctx, item_ref)
            if picked is not None:
                return picked
            if ctx.lang == "en":
                reply = "Tell me what you'd like to eat — chicken, fish, meat, salad, drinks, or say **restaurants**."
            else:
                reply = "قل لي ماذا تحب — دجاج، سمك، لحم، سلطة، مشروبات، أو **مطاعم**."
            return SkillResult(skill=SKILL_BUILD_CART, ok=False, action="need_preference", next_step=None, reply=reply)

        item = AbuuOrderDraftService.resolve_item_from_ref(
            ctx.abuu_db,
            restaurant_id=restaurant_id,
            item_ref=item_ref,
            context=ctx.context,
        )
        if item is None:
            cats = ctx.classification.categories
            if cats:
                return AbuuSkillRouter._menu_recommend(
                    TurnContext(
                        abuu_db=ctx.abuu_db,
                        main_db=ctx.main_db,
                        phone=ctx.phone,
                        text=ctx.text,
                        session=ctx.session,
                        customer=ctx.customer,
                        lang=ctx.lang,
                        message_id=ctx.message_id,
                        org_id=ctx.org_id,
                        classification=SkillClassification(
                            skill=SKILL_MENU_RECOMMEND,
                            categories=cats,
                            confidence=ctx.classification.confidence,
                        ),
                        context=ctx.context,
                        order=ctx.order,
                    )
                )
            if ctx.lang == "en":
                reply = "I couldn't find that item. Reply with the item name from the list."
            else:
                reply = "لم أجد هذا الصنف. أرسل اسم الصنف من القائمة."
            return SkillResult(skill=SKILL_BUILD_CART, ok=False, action="item_not_found", next_step="browsing", reply=reply)

        order = AbuuOrderDraftService.add_item(ctx.abuu_db, ctx.order, item)
        fingerprint = AbuuOrderDraftService.cart_fingerprint(ctx.abuu_db, order)
        context = AbuuOrderDraftService.mark_cart_changed(dict(ctx.context), fingerprint)
        cart_ids = list(context.get("cart_item_ids") or [])
        cart_ids.append(item.id)
        context["cart_item_ids"] = cart_ids
        context["last_main_item_type"] = item.item_type

        addon_msg, context = suggest_addons(
            ctx.abuu_db,
            restaurant_id=restaurant_id,
            main_item=item,
            active_categories=context.get("active_categories") or [],
            context=context,
            lang=ctx.lang,
        )
        AbuuOrderDraftService.upsert_session(
            ctx.abuu_db,
            phone=ctx.phone,
            step="browsing",
            context=context,
            active_order_id=order.id,
            message_id=ctx.message_id,
        )
        reply = item_added_message(item, order, ctx.lang, addon_hint=addon_msg)
        return SkillResult(
            skill=SKILL_BUILD_CART,
            ok=True,
            action="item_added",
            next_step="browsing",
            reply=reply,
            context_patch=context,
            extra={"order_id": order.id},
        )

    @staticmethod
    def _answer_kb(ctx: TurnContext) -> SkillResult:
        topic = ctx.classification.kb_topic
        restaurant_id = ctx.context.get("restaurant_id")
        settings = resolve_settings(ctx.abuu_db, restaurant_id=restaurant_id)
        if not topic:
            from app.abuu.services.kb_service import detect_kb_topic

            topic = detect_kb_topic(ctx.text)
        answer = answer_kb_question(settings, str(topic or ""), ctx.lang) if topic else None
        reply = answer or kb_fallback_message(ctx.lang)
        return SkillResult(
            skill=SKILL_ANSWER_KB,
            ok=bool(answer),
            action="kb_answer",
            next_step=ctx.session.step if ctx.session else None,
            reply=reply,
        )

    @staticmethod
    def _order_status(ctx: TurnContext) -> SkillResult:
        order = ctx.order
        if order is None:
            order = ctx.abuu_db.execute(
                select(CustomerOrder)
                .where(CustomerOrder.customer_id == ctx.customer.id)
                .order_by(CustomerOrder.created_at.desc())
            ).scalars().first()
        if order is None:
            if ctx.lang == "en":
                reply = "You don't have an active order. Send **abuu** to start."
            else:
                reply = "لا يوجد طلب نشط. أرسل **abuu** للبدء."
            return SkillResult(skill=SKILL_ORDER_STATUS, ok=False, action="no_order", next_step=None, reply=reply)
        assignment = ctx.abuu_db.execute(
            select(DeliveryAssignment).where(DeliveryAssignment.order_id == order.id)
        ).scalar_one_or_none()
        reply = order_status_message(order, assignment, ctx.lang)
        return SkillResult(skill=SKILL_ORDER_STATUS, ok=True, action="order_status", next_step=None, reply=reply)

    @staticmethod
    def _cancel_or_refund(ctx: TurnContext) -> SkillResult:
        settings = resolve_settings(ctx.abuu_db, restaurant_id=ctx.context.get("restaurant_id"))
        if ctx.order and ctx.order.status == "draft":
            AbuuOrderDraftService.cancel_draft(ctx.abuu_db, ctx.order)
            AbuuOrderDraftService.clear_session(ctx.abuu_db, ctx.phone)
            if ctx.lang == "en":
                reply = "Order cancelled. Send **abuu** to start again."
            else:
                reply = "تم إلغاء الطلب. أرسل **abuu** للبدء من جديد."
            return SkillResult(skill=SKILL_CANCEL_OR_REFUND, ok=True, action="cancelled", next_step="idle", reply=reply)
        policy = answer_kb_question(settings, "cancellation", ctx.lang) or answer_kb_question(settings, "refund", ctx.lang)
        reply = policy or kb_fallback_message(ctx.lang)
        return SkillResult(skill=SKILL_CANCEL_OR_REFUND, ok=True, action="policy_shared", next_step=None, reply=reply)

    @staticmethod
    def _handoff_to_admin(ctx: TurnContext) -> SkillResult:
        settings = resolve_settings(ctx.abuu_db)
        reply = answer_kb_question(settings, "escalation", ctx.lang) or kb_fallback_message(ctx.lang)
        return SkillResult(skill=SKILL_HANDOFF_TO_ADMIN, ok=True, action="handoff", next_step=None, reply=reply)

    @staticmethod
    def _capture_location_delegated(ctx: TurnContext) -> SkillResult:
        return SkillResult(
            skill=SKILL_CAPTURE_LOCATION,
            ok=False,
            action="delegate_inbound",
            next_step="awaiting_delivery",
            reply="",
        )

    @staticmethod
    def _confirm_order_delegated(ctx: TurnContext) -> SkillResult:
        return SkillResult(
            skill=SKILL_CONFIRM_ORDER,
            ok=False,
            action="delegate_inbound",
            next_step=None,
            reply="",
        )
