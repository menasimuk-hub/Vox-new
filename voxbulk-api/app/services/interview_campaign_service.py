"""Short campaign IDs for interview orders (tracking in reports and UI)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder

CAMPAIGN_PREFIX = "VB-CMP-"


def generate_campaign_id() -> str:
    return f"{CAMPAIGN_PREFIX}{uuid.uuid4().hex[:8].upper()}"


def ensure_campaign_id(db: Session, order: ServiceOrder) -> ServiceOrder:
    if order.service_code != "interview":
        return order
    if str(order.campaign_id or "").strip():
        return order
    for _ in range(8):
        candidate = generate_campaign_id()
        clash = db.execute(select(ServiceOrder.id).where(ServiceOrder.campaign_id == candidate)).scalar_one_or_none()
        if not clash:
            order.campaign_id = candidate
            db.add(order)
            db.commit()
            db.refresh(order)
            return order
    raise ValueError("Could not allocate campaign ID")
