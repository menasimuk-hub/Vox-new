"""Driver assignment, accept/reject, reassign."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import AbuuAssignmentAttempt, CustomerOrder, DeliveryAssignment, Driver
from app.abuu.services.notification_service import AbuuNotificationService

logger = logging.getLogger(__name__)

POST_ASSIGNMENT_STATUSES = {"assigned", "accepted", "on_route", "picked_up", "delivered"}


class AbuuDriverAssignmentService:
    @staticmethod
    def log_attempt(
        db: Session,
        *,
        order_id: str,
        assignment_id: str | None,
        driver_id: str | None,
        status: str,
        reason: str | None = None,
    ) -> AbuuAssignmentAttempt:
        row = AbuuAssignmentAttempt(
            order_id=order_id,
            assignment_id=assignment_id,
            driver_id=driver_id,
            status=status,
            reason=reason,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def excluded_driver_ids(db: Session, order_id: str) -> set[str]:
        rows = db.execute(
            select(AbuuAssignmentAttempt.driver_id).where(
                AbuuAssignmentAttempt.order_id == order_id,
                AbuuAssignmentAttempt.driver_id.isnot(None),
                AbuuAssignmentAttempt.status.in_(("rejected", "timed_out", "failed")),
            )
        ).scalars().all()
        return {d for d in rows if d}

    @staticmethod
    def pick_next_driver(db: Session, order_id: str) -> Driver | None:
        excluded = AbuuDriverAssignmentService.excluded_driver_ids(db, order_id)
        stmt = (
            select(Driver)
            .where(
                Driver.is_deleted.is_(False),
                Driver.is_available.is_(True),
                Driver.status == "active",
            )
            .order_by(Driver.created_at.asc())
        )
        for driver in db.execute(stmt).scalars().all():
            if driver.id not in excluded:
                return driver
        return None

    @staticmethod
    def reassign_driver(db: Session, order: CustomerOrder, *, reason: str | None = None) -> DeliveryAssignment | None:
        assignment = db.execute(
            select(DeliveryAssignment).where(DeliveryAssignment.order_id == order.id)
        ).scalars().first()
        driver = AbuuDriverAssignmentService.pick_next_driver(db, order.id)
        if driver is None:
            logger.error("abuu_driver_assignment_failed order_id=%s reason=no_available_driver", order.id)
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
            assignment.accepted_at = None
            assignment.rejected_at = None
            assignment.timed_out_at = None
            assignment.failure_reason = None
            assignment.updated_at = datetime.utcnow()
            db.add(assignment)

        AbuuDriverAssignmentService.log_attempt(
            db,
            order_id=order.id,
            assignment_id=assignment.id,
            driver_id=driver.id,
            status="assigned",
            reason=reason,
        )
        if order.status == "ready":
            from app.abuu.services.order_service import AbuuOrderService

            AbuuOrderService.patch_status(db, order, "assigned_to_driver")
        AbuuNotificationService.notify_driver_assigned(db, order, driver, assignment)
        logger.info("abuu_driver_reassigned order_id=%s driver_id=%s", order.id, driver.id)
        db.flush()
        return assignment
