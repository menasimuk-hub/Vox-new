"""Draft orders and conversation session state."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import (
    AbuuConversationSession,
    AbuuPayment,
    CustomerOrder,
    CustomerOrderItem,
    CustomerProfile,
    Restaurant,
    RestaurantMenuCategory,
    RestaurantMenuItem,
)
from app.abuu.services.customer_memory_service import parse_dislikes
from app.abuu.services.location_service import find_nearest_restaurants
from app.abuu.services.order_service import AbuuOrderService
from app.abuu.services.preference_service import category_keywords, item_types_for_categories
from app.abuu.services.reply_service import localized_name


class AbuuOrderDraftService:
    @staticmethod
    def get_session(db: Session, phone: str) -> AbuuConversationSession | None:
        return db.execute(
            select(AbuuConversationSession).where(AbuuConversationSession.customer_phone == phone)
        ).scalar_one_or_none()

    @staticmethod
    def upsert_session(
        db: Session,
        *,
        phone: str,
        step: str,
        context: dict | None = None,
        active_order_id: str | None = None,
        message_id: str | None = None,
    ) -> AbuuConversationSession:
        from app.abuu.agent.session_persist import prepare_context_for_storage

        stored_context = prepare_context_for_storage(context or {})
        row = AbuuOrderDraftService.get_session(db, phone)
        now = datetime.utcnow()
        if row is None:
            row = AbuuConversationSession(
                customer_phone=phone,
                step=step,
                context_json=json.dumps(stored_context),
                active_order_id=active_order_id,
                last_message_id=message_id,
                expires_at=now + timedelta(hours=24),
            )
        else:
            row.step = step
            row.context_json = json.dumps(stored_context)
            row.active_order_id = active_order_id
            row.last_message_id = message_id
            row.expires_at = now + timedelta(hours=24)
            row.updated_at = now
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def clear_session(db: Session, phone: str) -> None:
        row = AbuuOrderDraftService.get_session(db, phone)
        if row is not None:
            db.delete(row)

    @staticmethod
    def get_or_create_customer(db: Session, phone: str, *, lang: str = "ar") -> CustomerProfile:
        row = db.execute(select(CustomerProfile).where(CustomerProfile.phone == phone)).scalar_one_or_none()
        if row is not None:
            return row
        row = CustomerProfile(phone=phone, preferred_language=lang)
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def default_restaurant(db: Session, *, lat: float | None = None, lng: float | None = None) -> Restaurant | None:
        if lat is not None and lng is not None:
            ranked = find_nearest_restaurants(db, lat=lat, lng=lng, limit=1)
            if ranked:
                return ranked[0].restaurant
        return db.execute(
            select(Restaurant)
            .where(
                Restaurant.is_deleted.is_(False),
                Restaurant.is_available.is_(True),
                Restaurant.status == "active",
            )
            .order_by(Restaurant.created_at.asc())
        ).scalars().first()

    @staticmethod
    def list_menu_items(
        db: Session,
        restaurant_id: str,
        *,
        limit: int = 12,
        categories: list[str] | None = None,
        customer: CustomerProfile | None = None,
        allergen_avoid: list[str] | None = None,
        dietary_required: list[str] | None = None,
    ) -> list[RestaurantMenuItem]:
        from app.core.config import get_settings

        if get_settings().abuu_menu_intelligence_enabled:
            from app.abuu.menu_intelligence.query import MenuQuery
            from app.abuu.menu_intelligence.search_service import MenuSearchService

            query = MenuQuery.from_categories(categories, limit=limit)
            if allergen_avoid:
                query.allergen_avoid = list(allergen_avoid)
            if dietary_required:
                query.dietary_required = list(dietary_required)
            return MenuSearchService.search(db, restaurant_id, query, customer=customer)

        category_ids = [
            c.id
            for c in db.execute(
                select(RestaurantMenuCategory).where(
                    RestaurantMenuCategory.restaurant_id == restaurant_id,
                    RestaurantMenuCategory.is_deleted.is_(False),
                    RestaurantMenuCategory.is_available.is_(True),
                )
            ).scalars().all()
        ]
        if not category_ids:
            return []
        allowed_types = item_types_for_categories(categories or [])
        dislikes = parse_dislikes(customer) if customer is not None else []
        rows = list(
            db.execute(
                select(RestaurantMenuItem)
                .where(
                    RestaurantMenuItem.category_id.in_(category_ids),
                    RestaurantMenuItem.is_deleted.is_(False),
                    RestaurantMenuItem.is_available.is_(True),
                    RestaurantMenuItem.item_type.in_(tuple(allowed_types)),
                )
                .order_by(RestaurantMenuItem.item_type.asc(), RestaurantMenuItem.created_at.asc())
                .limit(max(limit, 50))
            ).scalars().all()
        )
        if not categories:
            return rows[:limit]

        filtered: list[RestaurantMenuItem] = []
        keywords = [kw.lower() for cat in categories for kw in category_keywords(cat)]
        for item in rows:
            haystack = f"{item.name_en} {item.name_ar} {item.item_type}".lower()
            if keywords and not any(kw in haystack for kw in keywords):
                if item.item_type not in item_types_for_categories(categories):
                    continue
            if any(dislike in haystack for dislike in dislikes):
                continue
            filtered.append(item)
            if len(filtered) >= limit:
                break
        return filtered or rows[:limit]

    @staticmethod
    def cart_fingerprint(db: Session, order: CustomerOrder) -> str:
        lines = db.execute(
            select(CustomerOrderItem).where(CustomerOrderItem.order_id == order.id)
        ).scalars().all()
        payload = {
            "total_agorot": int(order.total_agorot or 0),
            "items": sorted(
                [
                    {
                        "menu_item_id": line.menu_item_id,
                        "quantity": line.quantity,
                        "unit_price_agorot": line.unit_price_agorot,
                    }
                    for line in lines
                ],
                key=lambda row: row["menu_item_id"],
            ),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return digest[:16]

    @staticmethod
    def mark_cart_changed(context: dict, fingerprint: str) -> dict:
        context = dict(context or {})
        if context.get("cart_fingerprint") != fingerprint:
            context.pop("confirmed_cart_fingerprint", None)
        context["cart_fingerprint"] = fingerprint
        return context

    @staticmethod
    def build_suggestion_index(items: list[RestaurantMenuItem]) -> list[dict]:
        return [{"idx": i + 1, "menu_item_id": item.id} for i, item in enumerate(items)]

    @staticmethod
    def resolve_item_from_ref(
        db: Session,
        *,
        restaurant_id: str,
        item_ref: str,
        context: dict,
    ) -> RestaurantMenuItem | None:
        ref = str(item_ref or "").strip()
        suggestions = context.get("suggested_items") or []
        if ref.isdigit():
            idx = int(ref)
            for entry in suggestions:
                if int(entry.get("idx") or 0) == idx:
                    return db.get(RestaurantMenuItem, str(entry.get("menu_item_id")))
        lowered = ref.lower()
        for item in AbuuOrderDraftService.list_menu_items(db, restaurant_id, limit=50):
            if lowered in localized_name(item, "ar").lower() or lowered in localized_name(item, "en").lower():
                return item
        return None

    @staticmethod
    def list_addon_items(db: Session, restaurant_id: str, *, limit: int = 20) -> list[RestaurantMenuItem]:
        category_ids = [
            c.id
            for c in db.execute(
                select(RestaurantMenuCategory).where(
                    RestaurantMenuCategory.restaurant_id == restaurant_id,
                    RestaurantMenuCategory.is_deleted.is_(False),
                    RestaurantMenuCategory.is_available.is_(True),
                )
            ).scalars().all()
        ]
        if not category_ids:
            return []
        return list(
            db.execute(
                select(RestaurantMenuItem)
                .where(
                    RestaurantMenuItem.category_id.in_(category_ids),
                    RestaurantMenuItem.is_deleted.is_(False),
                    RestaurantMenuItem.is_available.is_(True),
                    RestaurantMenuItem.item_type.in_(("addon", "drink", "drinks", "salad", "sides", "desserts")),
                )
                .order_by(RestaurantMenuItem.item_type.asc(), RestaurantMenuItem.created_at.asc())
                .limit(limit)
            ).scalars().all()
        )

    @staticmethod
    def ensure_order(
        db: Session,
        *,
        customer: CustomerProfile,
        restaurant: Restaurant,
        existing_order: CustomerOrder | None = None,
        allow_switch: bool = False,
        context: dict | None = None,
    ) -> CustomerOrder:
        ctx = context or {}
        if existing_order is not None:
            if existing_order.restaurant_id != restaurant.id and existing_order.status == "draft":
                has_items = int(existing_order.total_agorot or 0) > 0
                is_bound = has_items or bool(ctx.get("restaurant_selected") and existing_order.restaurant_id)
                if is_bound and not allow_switch:
                    from app.abuu.conversation.restaurant_guard import RestaurantMismatchError

                    raise RestaurantMismatchError(
                        bound_id=str(existing_order.restaurant_id),
                        target_id=restaurant.id,
                        target_name=restaurant.name_ar or restaurant.name_en or restaurant.id,
                    )
                if is_bound and allow_switch:
                    from app.abuu.conversation.restaurant_guard import switch_restaurant_order

                    return switch_restaurant_order(
                        db,
                        customer=customer,
                        order=existing_order,
                        restaurant=restaurant,
                    )
                if not is_bound:
                    existing_order.restaurant_id = restaurant.id
                    existing_order.updated_at = datetime.utcnow()
                    db.add(existing_order)
                    db.flush()
            return existing_order
        return AbuuOrderDraftService.start_draft(db, customer=customer, restaurant=restaurant)

    @staticmethod
    def start_draft(db: Session, *, customer: CustomerProfile, restaurant: Restaurant) -> CustomerOrder:
        order = CustomerOrder(
            customer_id=customer.id,
            restaurant_id=restaurant.id,
            status="draft",
            payment_status="unpaid",
            total_agorot=0,
            currency="ILS",
        )
        db.add(order)
        db.flush()
        AbuuOrderService.append_event(db, order.id, "order_started", {"restaurant_id": restaurant.id})
        return order

    @staticmethod
    def add_item(db: Session, order: CustomerOrder, item: RestaurantMenuItem, *, quantity: int = 1) -> CustomerOrder:
        qty = max(1, int(quantity))
        line_total = item.price_agorot * qty
        db.add(
            CustomerOrderItem(
                order_id=order.id,
                menu_item_id=item.id,
                name_en=item.name_en,
                name_ar=item.name_ar,
                item_type=item.item_type,
                quantity=qty,
                unit_price_agorot=item.price_agorot,
                line_total_agorot=line_total,
            )
        )
        order.total_agorot = int(order.total_agorot or 0) + line_total
        order.updated_at = datetime.utcnow()
        db.add(order)
        AbuuOrderService.append_event(
            db,
            order.id,
            "item_added",
            {"menu_item_id": item.id, "quantity": qty, "line_total_agorot": line_total},
        )
        from app.abuu.services.customer_memory_service import remember_preference

        customer = db.get(CustomerProfile, order.customer_id)
        if customer is not None and item.item_type:
            remember_preference(customer, category=str(item.item_type))
            db.add(customer)
        return order

    @staticmethod
    def remove_item(
        db: Session,
        order: CustomerOrder,
        *,
        menu_item_id: str | None = None,
        item_id: str | None = None,
    ) -> CustomerOrder:
        target_id = menu_item_id or item_id
        if not target_id:
            raise ValueError("menu_item_id is required")
        line = db.execute(
            select(CustomerOrderItem).where(
                CustomerOrderItem.order_id == order.id,
                CustomerOrderItem.menu_item_id == target_id,
            )
        ).scalar_one_or_none()
        if line is None:
            raise ValueError("Item not in cart")
        order.total_agorot = max(0, int(order.total_agorot or 0) - int(line.line_total_agorot or 0))
        order.updated_at = datetime.utcnow()
        db.delete(line)
        db.add(order)
        AbuuOrderService.append_event(
            db,
            order.id,
            "item_removed",
            {"menu_item_id": target_id},
        )
        return order

    @staticmethod
    def confirm_draft(db: Session, order: CustomerOrder, *, allergy_note: str | None = None) -> CustomerOrder:
        if order.total_agorot <= 0:
            raise ValueError("Cannot confirm an empty order")
        if allergy_note:
            order.allergy_note = str(allergy_note).strip()[:512]
            db.add(order)
        AbuuOrderService.patch_status(db, order, "confirmed")
        payment = db.execute(select(AbuuPayment).where(AbuuPayment.order_id == order.id)).scalar_one_or_none()
        if payment is None:
            payment = AbuuPayment(
                order_id=order.id,
                status="pending_manual",
                amount_agorot=order.total_agorot,
            )
        else:
            payment.status = "pending_manual"
            payment.amount_agorot = order.total_agorot
            payment.updated_at = datetime.utcnow()
        db.add(payment)
        order.payment_status = "pending_manual"
        AbuuOrderService.append_event(db, order.id, "awaiting_manual_payment", {"total_agorot": order.total_agorot})
        customer = db.get(CustomerProfile, order.customer_id)
        if customer is not None:
            customer.order_count = int(customer.order_count or 0) + 1
            db.add(customer)
        return order

    @staticmethod
    def cancel_draft(db: Session, order: CustomerOrder | None) -> None:
        if order is None:
            return
        if order.status in {"draft", "confirmed"}:
            order.status = "cancelled"
            order.updated_at = datetime.utcnow()
            db.add(order)
            AbuuOrderService.append_event(db, order.id, "order_cancelled", {})
        elif order.status in {"sent_to_restaurant", "preparing"}:
            AbuuOrderService.cancel_paid_order(db, order, reason="customer_cancel")
