"""Internal Abuu notifications (restaurant/driver portals)."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import (
    AbuuNotification,
    CustomerOrder,
    DeliveryAssignment,
    Driver,
    Restaurant,
)


class AbuuNotificationService:
    @staticmethod
    def create(
        db: Session,
        *,
        target_type: str,
        target_id: str,
        order_id: str,
        kind: str,
        title: str,
        body: str,
        payload: dict | None = None,
    ) -> AbuuNotification:
        row = AbuuNotification(
            target_type=target_type,
            target_id=target_id,
            order_id=order_id,
            kind=kind,
            title=title,
            body=body,
            payload_json=json.dumps(payload or {}),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def notify_order_paid(db: Session, order: CustomerOrder) -> AbuuNotification:
        restaurant = db.get(Restaurant, order.restaurant_id)
        name = restaurant.name_ar if restaurant else "Restaurant"
        return AbuuNotificationService.create(
            db,
            target_type="restaurant",
            target_id=order.restaurant_id,
            order_id=order.id,
            kind="order_paid",
            title="طلب جديد مدفوع",
            body=f"طلب مدفوع جديد — {name} — {order.total_agorot / 100:.2f} ₪",
            payload={"order_id": order.id, "total_agorot": order.total_agorot},
        )

    @staticmethod
    def notify_driver_assigned(
        db: Session,
        order: CustomerOrder,
        driver: Driver,
        assignment: DeliveryAssignment,
    ) -> AbuuNotification:
        restaurant = db.get(Restaurant, order.restaurant_id)
        pickup = restaurant.address_text if restaurant else ""
        return AbuuNotificationService.create(
            db,
            target_type="driver",
            target_id=driver.id,
            order_id=order.id,
            kind="order_ready",
            title="طلب جاهز للاستلام",
            body=f"استلام من {restaurant.name_ar if restaurant else 'مطعم'} — {pickup}",
            payload={
                "order_id": order.id,
                "assignment_id": assignment.id,
                "restaurant_name": restaurant.name_ar if restaurant else None,
                "pickup_address": pickup,
            },
        )

    @staticmethod
    def notify_order_delivered(db: Session, order: CustomerOrder) -> AbuuNotification:
        return AbuuNotificationService.create(
            db,
            target_type="restaurant",
            target_id=order.restaurant_id,
            order_id=order.id,
            kind="order_delivered",
            title="تم التوصيل",
            body=f"تم توصيل الطلب {order.id[:8]}",
            payload={"order_id": order.id},
        )

    @staticmethod
    def list_for_target(
        db: Session,
        *,
        target_type: str,
        target_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[AbuuNotification]:
        stmt = (
            select(AbuuNotification)
            .where(AbuuNotification.target_type == target_type, AbuuNotification.target_id == target_id)
            .order_by(AbuuNotification.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            stmt = stmt.where(AbuuNotification.read_at.is_(None))
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def mark_read(db: Session, notification_id: str, *, target_type: str, target_id: str) -> AbuuNotification | None:
        row = db.get(AbuuNotification, notification_id)
        if row is None or row.target_type != target_type or row.target_id != target_id:
            return None
        row.read_at = datetime.utcnow()
        db.add(row)
        return row
