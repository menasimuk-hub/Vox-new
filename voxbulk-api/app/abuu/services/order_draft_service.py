"""Draft orders and conversation session state."""

from __future__ import annotations

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
from app.abuu.services.order_service import AbuuOrderService
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
        row = AbuuOrderDraftService.get_session(db, phone)
        now = datetime.utcnow()
        if row is None:
            row = AbuuConversationSession(
                customer_phone=phone,
                step=step,
                context_json=json.dumps(context or {}),
                active_order_id=active_order_id,
                last_message_id=message_id,
                expires_at=now + timedelta(hours=24),
            )
        else:
            row.step = step
            row.context_json = json.dumps(context or {})
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
    def default_restaurant(db: Session) -> Restaurant | None:
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
    def list_menu_items(db: Session, restaurant_id: str, *, limit: int = 12) -> list[RestaurantMenuItem]:
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
                    RestaurantMenuItem.item_type.in_(("meat", "food", "drink", "drinks", "salad", "sides", "desserts")),
                )
                .order_by(RestaurantMenuItem.item_type.asc(), RestaurantMenuItem.created_at.asc())
                .limit(limit)
            ).scalars().all()
        )

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
        return order

    @staticmethod
    def confirm_draft(db: Session, order: CustomerOrder) -> CustomerOrder:
        if order.total_agorot <= 0:
            raise ValueError("Cannot confirm an empty order")
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
