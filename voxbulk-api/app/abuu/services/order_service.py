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
from app.abuu.services.driver_assignment_service import AbuuDriverAssignmentService
from app.abuu.services.event_idempotency_service import AbuuEventIdempotencyService
from app.abuu.services.notification_service import AbuuNotificationService
from app.abuu.services.serializers import assignment_to_dict, event_to_dict, order_to_dict

logger = logging.getLogger(__name__)

ORDER_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"confirmed", "cancelled"},
    "confirmed": {"paid", "cancelled"},
    "paid": {"sent_to_restaurant", "cancelled"},
    "sent_to_restaurant": {"preparing", "cancelled"},
    "preparing": {"ready", "cancelled"},
    "ready": {"assigned_to_driver"},
    "assigned_to_driver": {"picked_up", "ready"},
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
        idem_key = f"order:{order.id}:paid"
        event = AbuuEventIdempotencyService.begin_event(
            db,
            source="admin",
            event_type="mark_paid",
            idempotency_key=idem_key,
            order_id=order.id,
            payload={"confirmed_by": confirmed_by},
        )
        if event.is_duplicate:
            if order.status in {"paid", "sent_to_restaurant", "preparing", "ready", "assigned_to_driver", "picked_up", "delivered"}:
                return order
            raise ValueError("Duplicate mark-paid event for order in unexpected status")

        if order.status in {"paid", "sent_to_restaurant", "preparing", "ready", "assigned_to_driver", "picked_up", "delivered"}:
            return order

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
        idem_key = f"order:{order.id}:ready"
        event = AbuuEventIdempotencyService.begin_event(
            db,
            source="restaurant",
            event_type="mark_ready",
            idempotency_key=idem_key,
            order_id=order.id,
            payload={},
        )
        if event.is_duplicate:
            if order.status in {"ready", "assigned_to_driver", "picked_up", "delivered"}:
                return order
            raise ValueError("Duplicate mark-ready event for order in unexpected status")

        if order.status in {"ready", "assigned_to_driver", "picked_up", "delivered"}:
            return order

        if order.status not in {"sent_to_restaurant", "preparing"}:
            raise ValueError("Order cannot be marked ready from current status")
        if getattr(order, "substitution_pending", False):
            raise ValueError("Resolve pending item substitutions before marking ready")
        if order.status == "sent_to_restaurant":
            AbuuOrderService.patch_status(db, order, "preparing")
        AbuuOrderService.patch_status(db, order, "ready")
        AbuuOrderService.assign_driver_for_order(db, order)
        return order

    @staticmethod
    def assign_driver_for_order(db: Session, order: CustomerOrder) -> DeliveryAssignment | None:
        if order.status not in {"ready", "assigned_to_driver"}:
            raise ValueError("Order must be ready before driver assignment")

        assignment = db.execute(
            select(DeliveryAssignment).where(DeliveryAssignment.order_id == order.id)
        ).scalars().first()
        if assignment and assignment.status in {"assigned", "accepted", "on_route", "picked_up"}:
            return assignment

        return AbuuDriverAssignmentService.reassign_driver(db, order)

    @staticmethod
    def driver_accept_assignment(db: Session, assignment: DeliveryAssignment) -> DeliveryAssignment:
        if assignment.status not in {"assigned", "unassigned"}:
            raise ValueError("Assignment cannot be accepted from current status")
        idem_key = f"assignment:{assignment.id}:accept"
        event = AbuuEventIdempotencyService.begin_event(
            db,
            source="driver",
            event_type="driver_accept",
            idempotency_key=idem_key,
            order_id=assignment.order_id,
            payload={"assignment_id": assignment.id},
        )
        if event.is_duplicate and assignment.accepted_at:
            return assignment

        assignment.status = "accepted"
        assignment.accepted_at = datetime.utcnow()
        assignment.updated_at = datetime.utcnow()
        db.add(assignment)
        AbuuDriverAssignmentService.log_attempt(
            db,
            order_id=assignment.order_id,
            assignment_id=assignment.id,
            driver_id=assignment.driver_id,
            status="accepted",
        )
        db.flush()
        return assignment

    @staticmethod
    def driver_reject_assignment(
        db: Session,
        assignment: DeliveryAssignment,
        *,
        reason: str | None = None,
    ) -> DeliveryAssignment | None:
        if assignment.status not in {"assigned", "accepted", "unassigned"}:
            raise ValueError("Assignment cannot be rejected from current status")

        idem_key = f"assignment:{assignment.id}:reject"
        event = AbuuEventIdempotencyService.begin_event(
            db,
            source="driver",
            event_type="driver_reject",
            idempotency_key=idem_key,
            order_id=assignment.order_id,
            payload={"reason": reason},
        )
        if event.is_duplicate:
            return db.execute(
                select(DeliveryAssignment).where(DeliveryAssignment.order_id == assignment.order_id)
            ).scalars().first()

        assignment.status = "rejected"
        assignment.rejected_at = datetime.utcnow()
        assignment.failure_reason = reason
        assignment.updated_at = datetime.utcnow()
        db.add(assignment)
        AbuuDriverAssignmentService.log_attempt(
            db,
            order_id=assignment.order_id,
            assignment_id=assignment.id,
            driver_id=assignment.driver_id,
            status="rejected",
            reason=reason,
        )
        logger.info("abuu_driver_rejected order_id=%s driver_id=%s", assignment.order_id, assignment.driver_id)

        order = db.get(CustomerOrder, assignment.order_id)
        if order is None:
            raise ValueError("Order not found")
        order.status = "ready"
        order.updated_at = datetime.utcnow()
        db.add(order)
        AbuuOrderService.append_event(db, order.id, "driver_rejected", {"reason": reason})
        return AbuuDriverAssignmentService.reassign_driver(db, order, reason=reason)

    @staticmethod
    def assignment_timeout(db: Session, assignment: DeliveryAssignment) -> DeliveryAssignment | None:
        if assignment.status not in {"assigned", "unassigned"}:
            raise ValueError("Assignment cannot time out from current status")

        idem_key = f"assignment:{assignment.id}:timeout"
        event = AbuuEventIdempotencyService.begin_event(
            db,
            source="admin",
            event_type="driver_timeout",
            idempotency_key=idem_key,
            order_id=assignment.order_id,
            payload={},
        )
        if event.is_duplicate:
            return assignment

        assignment.status = "timed_out"
        assignment.timed_out_at = datetime.utcnow()
        assignment.updated_at = datetime.utcnow()
        db.add(assignment)
        AbuuDriverAssignmentService.log_attempt(
            db,
            order_id=assignment.order_id,
            assignment_id=assignment.id,
            driver_id=assignment.driver_id,
            status="timed_out",
        )

        order = db.get(CustomerOrder, assignment.order_id)
        if order is None:
            raise ValueError("Order not found")
        order.status = "ready"
        order.updated_at = datetime.utcnow()
        db.add(order)
        return AbuuDriverAssignmentService.reassign_driver(db, order, reason="timeout")

    @staticmethod
    def driver_fail_pickup(
        db: Session,
        assignment: DeliveryAssignment,
        *,
        reason: str | None = None,
    ) -> DeliveryAssignment | None:
        if assignment.status not in {"assigned", "accepted", "on_route"}:
            raise ValueError("Assignment cannot fail from current status")

        idem_key = f"assignment:{assignment.id}:fail"
        AbuuEventIdempotencyService.begin_event(
            db,
            source="driver",
            event_type="driver_fail_pickup",
            idempotency_key=idem_key,
            order_id=assignment.order_id,
            payload={"reason": reason},
        )

        assignment.status = "failed"
        assignment.failure_reason = reason
        assignment.updated_at = datetime.utcnow()
        db.add(assignment)
        AbuuDriverAssignmentService.log_attempt(
            db,
            order_id=assignment.order_id,
            assignment_id=assignment.id,
            driver_id=assignment.driver_id,
            status="failed",
            reason=reason,
        )
        logger.error("abuu_driver_assignment_failed order_id=%s reason=%s", assignment.order_id, reason)

        order = db.get(CustomerOrder, assignment.order_id)
        if order is None:
            raise ValueError("Order not found")
        order.status = "ready"
        order.updated_at = datetime.utcnow()
        db.add(order)
        return AbuuDriverAssignmentService.reassign_driver(db, order, reason=reason)

    @staticmethod
    def driver_mark_picked_up(db: Session, assignment: DeliveryAssignment) -> CustomerOrder:
        order = db.get(CustomerOrder, assignment.order_id)
        if order is None:
            raise ValueError("Order not found")
        if assignment.status not in {"assigned", "accepted", "unassigned"}:
            raise ValueError("Assignment cannot be picked up from current status")
        assignment.status = "on_route"
        assignment.picked_up_at = datetime.utcnow()
        assignment.updated_at = datetime.utcnow()
        db.add(assignment)
        AbuuDriverAssignmentService.log_attempt(
            db,
            order_id=assignment.order_id,
            assignment_id=assignment.id,
            driver_id=assignment.driver_id,
            status="picked_up",
        )
        AbuuOrderService.patch_status(db, order, "picked_up")
        return order

    @staticmethod
    def driver_mark_delivered(db: Session, assignment: DeliveryAssignment) -> CustomerOrder:
        order = db.get(CustomerOrder, assignment.order_id)
        if order is None:
            raise ValueError("Order not found")
        if assignment.status not in {"on_route", "picked_up", "assigned", "accepted"}:
            raise ValueError("Assignment cannot be delivered from current status")
        assignment.status = "delivered"
        assignment.delivered_at = datetime.utcnow()
        assignment.updated_at = datetime.utcnow()
        db.add(assignment)
        AbuuDriverAssignmentService.log_attempt(
            db,
            order_id=assignment.order_id,
            assignment_id=assignment.id,
            driver_id=assignment.driver_id,
            status="delivered",
        )
        AbuuOrderService.patch_status(db, order, "delivered")
        AbuuNotificationService.notify_order_delivered(db, order)
        return order

    @staticmethod
    def cancel_paid_order(
        db: Session,
        order: CustomerOrder,
        *,
        reason: str | None = None,
        actor: str = "admin",
    ) -> CustomerOrder:
        if order.status not in {"sent_to_restaurant", "preparing"}:
            raise ValueError("Paid order can only be cancelled before ready")
        order.status = "cancelled"
        order.refund_ready = True
        order.cancelled_reason = reason
        order.updated_at = datetime.utcnow()
        db.add(order)
        AbuuOrderService.append_event(db, order.id, "order_cancelled_paid", {"reason": reason, "actor": actor})
        AbuuNotificationService.notify_order_cancelled_paid(db, order)
        AbuuEventIdempotencyService.begin_event(
            db,
            source="admin",
            event_type="cancel_paid",
            idempotency_key=f"order:{order.id}:cancel_paid",
            order_id=order.id,
            payload={"reason": reason},
        )
        return order

    @staticmethod
    def mark_refund_processed(db: Session, order: CustomerOrder) -> CustomerOrder:
        if not order.refund_ready:
            raise ValueError("Order is not flagged for refund")
        order.refund_ready = False
        order.updated_at = datetime.utcnow()
        db.add(order)
        AbuuOrderService.append_event(db, order.id, "refund_processed", {})
        return order

    @staticmethod
    def set_prep_delay_note(db: Session, order: CustomerOrder, note: str) -> CustomerOrder:
        order.prep_delay_note = note.strip() or None
        order.updated_at = datetime.utcnow()
        db.add(order)
        AbuuOrderService.append_event(db, order.id, "prep_delay", {"note": note})
        return order

    @staticmethod
    def admin_recover(
        db: Session,
        order: CustomerOrder,
        *,
        action: str,
        note: str | None = None,
        actor: str = "admin",
    ) -> CustomerOrder:
        AbuuEventIdempotencyService.begin_event(
            db,
            source="admin",
            event_type="admin_recover",
            idempotency_key=f"order:{order.id}:recover:{action}:{datetime.utcnow().isoformat()}",
            order_id=order.id,
            payload={"action": action, "note": note},
        )
        if action == "clear_location_missing":
            order.location_missing = False
            order.location_clarification_sent = False
        elif action == "force_status" and note:
            order.status = note
        elif action == "reassign_driver":
            if order.status not in {"ready", "assigned_to_driver"}:
                order.status = "ready"
            AbuuDriverAssignmentService.reassign_driver(db, order, reason=note or "admin_recover")
        else:
            raise ValueError(f"Unknown recover action: {action}")

        order.updated_at = datetime.utcnow()
        db.add(order)
        AbuuOrderService.append_event(db, order.id, "admin_recover", {"action": action, "note": note, "actor": actor})
        return order

    @staticmethod
    def get_order_detail(db: Session, order_id: str) -> dict | None:
        order = db.get(CustomerOrder, order_id)
        if order is None or order.is_deleted:
            return None

        items_raw = db.execute(
            select(CustomerOrderItem).where(CustomerOrderItem.order_id == order.id)
        ).scalars().all()
        menu_ids = {i.menu_item_id for i in items_raw if not i.name_en and not i.name_ar}
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
                    "name_en": i.name_en or (menu.name_en if menu else None),
                    "name_ar": i.name_ar or (menu.name_ar if menu else None),
                    "item_type": i.item_type or (menu.item_type if menu else None),
                    "quantity": i.quantity,
                    "unit_price_agorot": i.unit_price_agorot,
                    "line_total_agorot": i.line_total_agorot,
                    "unavailable": getattr(i, "unavailable", False),
                    "substitution_status": getattr(i, "substitution_status", None),
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
        data["location_missing"] = order.location_missing
        data["location_clarification_sent"] = order.location_clarification_sent
        data["refund_ready"] = order.refund_ready
        data["prep_delay_note"] = order.prep_delay_note
        data["cancelled_reason"] = order.cancelled_reason
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
