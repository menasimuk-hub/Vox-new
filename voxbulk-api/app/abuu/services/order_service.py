"""Order lifecycle and admin payment confirmation."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import (
    AbuuPayment,
    CustomerOrder,
    DeliveryAssignment,
    Driver,
    OrderEvent,
)
from app.abuu.services.serializers import assignment_to_dict, event_to_dict, order_to_dict

ORDER_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_payment", "cancelled"},
    "pending_payment": {"paid", "cancelled"},
    "paid": {"preparing"},
    "preparing": {"dispatched"},
    "dispatched": {"delivered"},
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
        if order.status not in {"draft", "pending_payment"}:
            raise ValueError("Order cannot be marked paid from current status")
        if order.status == "draft":
            order.status = "pending_payment"
        AbuuOrderService.assert_status_transition(order.status, "paid")
        order.status = "paid"
        order.payment_status = "paid_manual"
        order.updated_at = datetime.utcnow()
        payment = db.execute(select(AbuuPayment).where(AbuuPayment.order_id == order.id)).scalar_one_or_none()
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
        assignment = db.execute(
            select(DeliveryAssignment).where(DeliveryAssignment.order_id == order.id)
        ).scalar_one_or_none()
        if assignment is None:
            driver = db.execute(
                select(Driver)
                .where(Driver.is_deleted.is_(False), Driver.is_available.is_(True), Driver.status == "active")
                .order_by(Driver.created_at.asc())
            ).scalar_one_or_none()
            assignment = DeliveryAssignment(
                order_id=order.id,
                driver_id=driver.id if driver else None,
                status="assigned" if driver else "unassigned",
                assigned_at=datetime.utcnow() if driver else None,
            )
            db.add(assignment)
        order.status = "preparing"
        order.updated_at = datetime.utcnow()
        AbuuOrderService.append_event(db, order.id, "status_changed", {"status": "preparing"})
        db.add(order)
        return order

    @staticmethod
    def get_order_detail(db: Session, order_id: str) -> dict | None:
        order = db.get(CustomerOrder, order_id)
        if order is None or order.is_deleted:
            return None
        from app.abuu.models.entities import CustomerOrderItem

        order_items = [
            {
                "id": i.id,
                "menu_item_id": i.menu_item_id,
                "quantity": i.quantity,
                "unit_price_agorot": i.unit_price_agorot,
                "line_total_agorot": i.line_total_agorot,
            }
            for i in db.execute(select(CustomerOrderItem).where(CustomerOrderItem.order_id == order.id)).scalars().all()
        ]
        events = [
            event_to_dict(e)
            for e in db.execute(
                select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.created_at.asc())
            ).scalars().all()
        ]
        assignment = db.execute(
            select(DeliveryAssignment).where(DeliveryAssignment.order_id == order.id)
        ).scalar_one_or_none()
        data = order_to_dict(order, items=order_items, events=events)
        data["assignment"] = assignment_to_dict(assignment) if assignment else None
        return data
