"""Interview task reference IDs for careers@ email routing."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder

REFERENCE_PREFIX = "VB-INT-"
REFERENCE_PATTERN = re.compile(r"\b(VB-INT-[A-Z0-9]{6,12})\b", re.IGNORECASE)


def generate_reference_id() -> str:
    token = uuid.uuid4().hex[:8].upper()
    return f"{REFERENCE_PREFIX}{token}"


def extract_reference_id(text: str) -> str | None:
    match = REFERENCE_PATTERN.search(str(text or ""))
    if not match:
        return None
    return match.group(1).upper()


def ensure_order_reference_id(db: Session, order: ServiceOrder) -> ServiceOrder:
    if order.service_code != "interview":
        return order
    if str(order.reference_id or "").strip():
        return order
    for _ in range(8):
        candidate = generate_reference_id()
        clash = db.execute(select(ServiceOrder.id).where(ServiceOrder.reference_id == candidate)).scalar_one_or_none()
        if not clash:
            order.reference_id = candidate
            db.add(order)
            db.commit()
            db.refresh(order)
            return order
    raise ValueError("Could not allocate interview reference ID")


def find_interview_order_by_reference(db: Session, reference_id: str) -> ServiceOrder | None:
    ref = str(reference_id or "").strip().upper()
    if not ref:
        return None
    return db.execute(
        select(ServiceOrder).where(
            ServiceOrder.service_code == "interview",
            ServiceOrder.reference_id == ref,
        )
    ).scalar_one_or_none()
