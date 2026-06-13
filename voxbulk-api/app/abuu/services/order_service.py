"""Order lifecycle, notifications, and admin payment confirmation."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import (
    AbuuPayment,
    CustomerAddress,
    CustomerOrder,
    CustomerOrderItem,
    CustomerProfile,
    DeliveryAssignment,
    Driver,
    OrderEvent,
    Restaurant,
    RestaurantMenuItem,
)
from app.abuu.services.notification_service import AbuuNotificationService
from app.abuu.services.serializers import assignment_to_dict, event_to_dict, order_to_dict

logger = logging.getLogger(__name__)

ORDER_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"confirmed", "cancelled"},
    "confirmed": {"paid", "cancelled"},
    "paid": {"sent_to_restaurant"},
    "sent_to_restaurant": {"preparing", "cancelled"},
    "preparing": {"ready", "cancelled"},
    "ready": {"assigned_to_driver"},
    "assigned_to_driver": {"picked_up"},
    "picked_up": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


class AbuuOrderService:
    @staticmethod
    def assert_status_transition(current: str, new: str) -> None:
        allowed = ORDER_STATUS_TRANSITIONS.get(current, set())
        if new not in allowed:
            raise ValueError(f"Cannot transition order from {current} to {new}")

    @staticmethod
    def append_event(db: Session, order_id: str, event_type: str, payload: dict | None = None) -> OrderEvent:
        row = OrderEvent(
            order_id=order_id,
            event_type=event_type,
            payload_json=json.dumps(payload or {}),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def patch_status(db: Session, order: CustomerOrder, new_status: str) -> CustomerOrder:
        AbuuOrderService.assert_status_transition(order.status, new_status)
        order.status = new_status
        order.updated_at = datetime.utcnow()
        AbuuOrderService.append_event(db, order.id, "status_changed", {"status": new_status})
        db.add(order)
        return order

    @staticmethod
    def mark_paid_manual(db: Session, order: CustomerOrder, *, confirmed_by: str) -> CustomerOrder:
        if order.status not in {"draft", "confirmed"}:
            raise ValueError("Order cannot be marked paid from current status")
        if order.status == "draft":
            order.status = "confirmed"
        AbuuOrderService.assert_status_transition(order.status, "paid")
        order.status = "paid"
        order.payment_status = "paid_manual"
        order.updated_at = datetime.utcnow()

        payment = db.execute(select(AbuuPayment).where(AbuuPayment.order_id == order.id)).scalars().first()
        if payment is None:
            payment = AbuuPayment(
                order_id=order.id,
                status="paid_manual",
                amount_agorot=order.total_agorot,
                confirmed_by=confirmed_by,
                confirmed_at=datetime.utcnow(),
            )
        else:
            payment.status = "paid_manual"
            payment.amount_agorot = order.total_agorot
            payment.confirmed_by = confirmed_by
            payment.confirmed_at = datetime.utcnow()
            payment.updated_at = datetime.utcnow()
        db.add(payment)
        AbuuOrderService.append_event(db, order.id, "payment_confirmed", {"confirmed_by": confirmed_by})

        AbuuOrderService.patch_status(db, order, "sent_to_restaurant")
        AbuuNotificationService.notify_order_paid(db, order)
        db.add(order)
        return order

    @staticmethod
    def restaurant_start_preparing(db: Session, order: CustomerOrder) -> CustomerOrder:
        if order.status != "sent_to_restaurant":
            raise ValueError("Order is not awaiting preparation")
        return AbuuOrderService.patch_status(db, order, "preparing")

    @staticmethod
    def restaurant_mark_ready(db: Session, order: CustomerOrder) -> CustomerOrder:
        if order.status not in {"sent_to_restaurant", "preparing"}:
            raise ValueError("Order cannot be marked ready from current status")
        if order.status == "sent_to_restaurant":
            AbuuOrderService.patch_status(db, order, "preparing")
        AbuuOrderService.patch_status(db, order, "ready")
        AbuuOrderService.assign_driver_for_order(db, order)
        return order

    @staticmethod
    def assign_driver_for_order(db: Session, order: CustomerOrder) -> DeliveryAssignment | None:
        if order.status != "ready":
            raise ValueError("Order must be ready before driver assignment")

        driver = db.execute(
            select(Driver)
            .where(Driver.is_deleted.is_(False), Driver.is_available.is_(True), Driver.status == "active")
            .order_by(Driver.created_at.asc())
            .limit(1)
        ).scalars().first()

        assignment = db.execute(
            select(DeliveryAssignment).where(DeliveryAssignment.order_id == order.id)
        ).scalars().first()

        if driver is None:
            logger.error(
                "abuu_driver_assignment_failed order_id=%s reason=no_available_driver",
                order.id,
            )
            if assignment is None:
                assignment = DeliveryAssignment(order_id=order.id, status="unassigned")
                db.add(assignment)
                db.flush()
            return assignment

        if assignment is None:
            assignment = DeliveryAssignment(
                order_id=order.id,
                driver_id=driver.id,
                status="assigned",
                assigned_at=datetime.utcnow(),
            )
            db.add(assignment)
        else:
            assignment.driver_id = driver.id
            assignment.status = "assigned"
            assignment.assigned_at = datetime.utcnow()
            assignment.updated_at = datetime.utcnow()
            db.add(assignment)

        AbuuOrderService.patch_status(db, order, "assigned_to_driver")
        AbuuNotificationService.notify_driver_assigned(db, order, driver, assignment)
        db.flush()
        return assignment

    @staticmethod
    def driver_mark_picked_up(db: Session, assignment: DeliveryAssignment) -> CustomerOrder:
        order = db.get(CustomerOrder, assignment.order_id)
        if order is None:
            raise ValueError("Order not found")
        if assignment.status not in {"assigned", "unassigned"}:
            raise ValueError("Assignment cannot be picked up from current status")
        assignment.status = "on_route"
        assignment.picked_up_at = datetime.utcnow()
        assignment.updated_at = datetime.utcnow()
        db.add(assignment)
        AbuuOrderService.patch_status(db, order, "picked_up")
        return order

    @staticmethod
    def driver_mark_delivered(db: Session, assignment: DeliveryAssignment) -> CustomerOrder:
        order = db.get(CustomerOrder, assignment.order_id)
        if order is None:
            raise ValueError("Order not found")
        if assignment.status not in {"on_route", "picked_up", "assigned"}:
            raise ValueError("Assignment cannot be delivered from current status")
        assignment.status = "delivered"
        assignment.delivered_at = datetime.utcnow()
        assignment.updated_at = datetime.utcnow()
        db.add(assignment)
        AbuuOrderService.patch_status(db, order, "delivered")
        AbuuNotificationService.notify_order_delivered(db, order)
        return order

    @staticmethod
    def get_order_detail(db: Session, order_id: str) -> dict | None:
        order = db.get(CustomerOrder, order_id)
        if order is None or order.is_deleted:
            return None

        items_raw = db.execute(
            select(CustomerOrderItem).where(CustomerOrderItem.order_id == order.id)
        ).scalars().all()
        menu_ids = {i.menu_item_id for i in items_raw}
        menu_map = {
            m.id: m
            for m in db.execute(select(RestaurantMenuItem).where(RestaurantMenuItem.id.in_(menu_ids))).scalars().all()
        } if menu_ids else {}

        order_items = []
        for i in items_raw:
            menu = menu_map.get(i.menu_item_id)
            order_items.append(
                {
                    "id": i.id,
                    "menu_item_id": i.menu_item_id,
                    "name_en": menu.name_en if menu else None,
                    "name_ar": menu.name_ar if menu else None,
                    "quantity": i.quantity,
                    "unit_price_agorot": i.unit_price_agorot,
                    "line_total_agorot": i.line_total_agorot,
                }
            )

        events = [
            event_to_dict(e)
            for e in db.execute(
                select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.created_at.asc())
            ).scalars().all()
        ]
        assignment = db.execute(
            select(DeliveryAssignment).where(DeliveryAssignment.order_id == order.id)
        ).scalars().first()

        customer = db.get(CustomerProfile, order.customer_id)
        restaurant = db.get(Restaurant, order.restaurant_id)
        address = db.get(CustomerAddress, order.delivery_address_id) if order.delivery_address_id else None

        data = order_to_dict(order, items=order_items, events=events)
        data["assignment"] = assignment_to_dict(assignment) if assignment else None
        data["customer"] = {
            "id": customer.id if customer else None,
            "phone": customer.phone if customer else None,
            "name": customer.name if customer else None,
        }
        data["restaurant"] = {
            "id": restaurant.id if restaurant else None,
            "name_en": restaurant.name_en if restaurant else None,
            "name_ar": restaurant.name_ar if restaurant else None,
            "address_text": restaurant.address_text if restaurant else None,
            "latitude": restaurant.latitude if restaurant else None,
            "longitude": restaurant.longitude if restaurant else None,
        }
        data["delivery_address"] = (
            {
                "id": address.id,
                "address_text": address.address_text,
                "latitude": address.latitude,
                "longitude": address.longitude,
            }
            if address
            else None
        )
        return data
