from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.core.auth import DriverPrincipal, require_driver_user
from app.abuu.models.entities import CustomerOrder, DeliveryAssignment, Driver
from app.abuu.services.serializers import assignment_to_dict, driver_to_dict, order_to_dict
from app.core.abuu_database import get_abuu_db

router = APIRouter(prefix="/abuu/driver", tags=["abuu-driver"])


@router.get("/me")
def driver_me(principal: DriverPrincipal = Depends(require_driver_user), db: Session = Depends(get_abuu_db)):
    row = db.get(Driver, principal.driver_id)
    return driver_to_dict(row)


@router.get("/assignments")
def driver_assignments(
    principal: DriverPrincipal = Depends(require_driver_user),
    db: Session = Depends(get_abuu_db),
):
    rows = db.execute(
        select(DeliveryAssignment)
        .where(DeliveryAssignment.driver_id == principal.driver_id)
        .order_by(DeliveryAssignment.created_at.desc())
    ).scalars().all()
    out = []
    for row in rows:
        payload = assignment_to_dict(row)
        order = db.get(CustomerOrder, row.order_id)
        payload["order"] = order_to_dict(order) if order else None
        out.append(payload)
    return out


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
    if new_status == "picked_up":
        row.status = "picked_up"
        row.picked_up_at = datetime.utcnow()
    elif new_status == "delivered":
        row.status = "delivered"
        row.delivered_at = datetime.utcnow()
    else:
        row.status = new_status
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return assignment_to_dict(row)
