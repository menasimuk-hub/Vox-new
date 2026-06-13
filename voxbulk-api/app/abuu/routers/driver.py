from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.core.auth import DriverPrincipal, require_driver_user
from app.abuu.models.entities import CustomerAddress, CustomerOrder, CustomerProfile, DeliveryAssignment, Driver, Restaurant
from app.abuu.services.notification_service import AbuuNotificationService
from app.abuu.services.order_service import AbuuOrderService
from app.abuu.services.serializers import assignment_to_dict, driver_to_dict, notification_to_dict
from app.core.abuu_database import get_abuu_db

router = APIRouter(prefix="/abuu/driver", tags=["abuu-driver"])

DRIVER_BOARD_STATUSES = {
    "assigned": {"assigned", "accepted", "unassigned"},
    "picked_up": {"on_route"},
    "on_route": {"on_route"},
    "delivered": {"delivered"},
    "failed": {"failed", "rejected", "timed_out"},
}


@router.get("/me")
def driver_me(principal: DriverPrincipal = Depends(require_driver_user), db: Session = Depends(get_abuu_db)):
    row = db.get(Driver, principal.driver_id)
    return driver_to_dict(row)


@router.get("/assignments")
def driver_assignments(
    board: str | None = Query(None),
    principal: DriverPrincipal = Depends(require_driver_user),
    db: Session = Depends(get_abuu_db),
):
    rows = db.execute(
        select(DeliveryAssignment)
        .where(DeliveryAssignment.driver_id == principal.driver_id)
        .order_by(DeliveryAssignment.created_at.desc())
    ).scalars().all()
    if board:
        allowed = DRIVER_BOARD_STATUSES.get(board.lower(), set())
        rows = [r for r in rows if r.status in allowed]

    out = []
    for row in rows:
        payload = _enriched_assignment(db, row)
        out.append(payload)
    return out


def _enriched_assignment(db: Session, row: DeliveryAssignment) -> dict:
    payload = assignment_to_dict(row)
    order = db.get(CustomerOrder, row.order_id)
    restaurant = db.get(Restaurant, order.restaurant_id) if order else None
    customer = db.get(CustomerProfile, order.customer_id) if order else None
    address = db.get(CustomerAddress, order.delivery_address_id) if order and order.delivery_address_id else None

    payload["order"] = AbuuOrderService.get_order_detail(db, row.order_id) if order else None
    payload["pickup"] = {
        "restaurant_name_en": restaurant.name_en if restaurant else None,
        "restaurant_name_ar": restaurant.name_ar if restaurant else None,
        "address_text": restaurant.address_text if restaurant else None,
        "latitude": restaurant.latitude if restaurant else None,
        "longitude": restaurant.longitude if restaurant else None,
    }
    payload["dropoff"] = {
        "customer_name": customer.name if customer else None,
        "customer_phone": customer.phone if customer else None,
        "address_text": address.address_text if address else None,
        "latitude": address.latitude if address else None,
        "longitude": address.longitude if address else None,
    }
    return payload


@router.patch("/assignments/{assignment_id}")
def patch_assignment(
    assignment_id: str,
    payload: dict,
    principal: DriverPrincipal = Depends(require_driver_user),
    db: Session = Depends(get_abuu_db),
):
    row = db.get(DeliveryAssignment, assignment_id)
    if row is None or row.driver_id != principal.driver_id:
        raise HTTPException(status_code=404, detail="Assignment not found")
    new_status = str(payload.get("status") or row.status)
    try:
        if new_status == "accepted":
            AbuuOrderService.driver_accept_assignment(db, row)
        elif new_status == "rejected":
            row = AbuuOrderService.driver_reject_assignment(db, row, reason=str(payload.get("reason") or ""))
        elif new_status == "picked_up":
            AbuuOrderService.driver_mark_picked_up(db, row)
        elif new_status == "delivered":
            AbuuOrderService.driver_mark_delivered(db, row)
        elif new_status == "failed":
            row = AbuuOrderService.driver_fail_pickup(db, row, reason=str(payload.get("reason") or ""))
        else:
            row.status = new_status
            row.updated_at = datetime.utcnow()
            db.add(row)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.refresh(row)
    return _enriched_assignment(db, row)


@router.get("/notifications")
def driver_notifications(
    unread_only: bool = False,
    principal: DriverPrincipal = Depends(require_driver_user),
    db: Session = Depends(get_abuu_db),
):
    rows = AbuuNotificationService.list_for_target(
        db,
        target_type="driver",
        target_id=principal.driver_id,
        unread_only=unread_only,
    )
    return [notification_to_dict(r) for r in rows]


@router.patch("/notifications/{notification_id}/read")
def driver_mark_notification_read(
    notification_id: str,
    principal: DriverPrincipal = Depends(require_driver_user),
    db: Session = Depends(get_abuu_db),
):
    row = AbuuNotificationService.mark_read(
        db,
        notification_id,
        target_type="driver",
        target_id=principal.driver_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.commit()
    return notification_to_dict(row)
