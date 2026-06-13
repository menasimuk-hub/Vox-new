"""Internal Abuu notifications (restaurant/driver portals)."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.abuu.models.entities import (
    AbuuNotification,
    CustomerOrder,
    DeliveryAssignment,
    Driver,
    Restaurant,
)

logger = logging.getLogger(__name__)


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
    def create_if_absent(
        db: Session,
        *,
        target_type: str,
        target_id: str,
        order_id: str,
        kind: str,
        title: str,
        body: str,
        payload: dict | None = None,
    ) -> AbuuNotification | None:
        existing = db.execute(
            select(AbuuNotification).where(
                AbuuNotification.order_id == order_id,
                AbuuNotification.kind == kind,
                AbuuNotification.target_type == target_type,
                AbuuNotification.target_id == target_id,
            )
        ).scalars().first()
        if existing is not None:
            return existing
        try:
            with db.begin_nested():
                return AbuuNotificationService.create(
                    db,
                    target_type=target_type,
                    target_id=target_id,
                    order_id=order_id,
                    kind=kind,
                    title=title,
                    body=body,
                    payload=payload,
                )
        except IntegrityError:
            return db.execute(
                select(AbuuNotification).where(
                    AbuuNotification.order_id == order_id,
                    AbuuNotification.kind == kind,
                    AbuuNotification.target_type == target_type,
                    AbuuNotification.target_id == target_id,
                )
            ).scalars().first()

    @staticmethod
    def notify_order_paid(db: Session, order: CustomerOrder) -> AbuuNotification | None:
        restaurant = db.get(Restaurant, order.restaurant_id)
        name = restaurant.name_ar if restaurant else "Restaurant"
        return AbuuNotificationService.create_if_absent(
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
    ) -> AbuuNotification | None:
        restaurant = db.get(Restaurant, order.restaurant_id)
        pickup = restaurant.address_text if restaurant else ""
        return AbuuNotificationService.create_if_absent(
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
    def notify_order_delivered(db: Session, order: CustomerOrder) -> AbuuNotification | None:
        return AbuuNotificationService.create_if_absent(
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
    def notify_order_cancelled_paid(db: Session, order: CustomerOrder) -> AbuuNotification | None:
        restaurant = db.get(Restaurant, order.restaurant_id)
        name = restaurant.name_ar if restaurant else "Restaurant"
        return AbuuNotificationService.create_if_absent(
            db,
            target_type="restaurant",
            target_id=order.restaurant_id,
            order_id=order.id,
            kind="order_cancelled",
            title="تم إلغاء الطلب",
            body=f"تم إلغاء طلب مدفوع — {name}",
            payload={"order_id": order.id, "refund_ready": order.refund_ready},
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
