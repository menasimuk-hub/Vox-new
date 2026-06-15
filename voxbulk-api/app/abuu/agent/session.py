"""Session adapter over Abuu conversation + draft order state."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerOrder, CustomerOrderItem, CustomerProfile
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_STEP_TO_STAGE = {
    "idle": "browsing",
    "awaiting_name": "browsing",
    "awaiting_preference": "browsing",
    "choosing_restaurant": "browsing",
    "browsing": "browsing",
    "awaiting_delivery": "confirming",
    "done": "done",
}

_STAGE_TO_STEP = {
    "browsing": "browsing",
    "confirming": "awaiting_delivery",
    "done": "done",
}


def _redis_client():
    try:
        import redis

        settings = get_settings()
        return redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.5)
    except Exception:
        return None


def _cache_key(phone: str) -> str:
    return f"abuu:session:{phone}"


def step_to_stage(step: str | None) -> str:
    return _STEP_TO_STAGE.get(str(step or "browsing"), "browsing")


def stage_to_step(stage: str) -> str:
    return _STAGE_TO_STEP.get(stage, "browsing")


@dataclass
class Session:
    customer_wa_number: str
    restaurant_id: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    cart: list[dict[str, Any]] = field(default_factory=list)
    stage: str = "browsing"
    language: str = "ar"
    active_order_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    customer_id: str | None = None

    def to_context_json(self) -> dict[str, Any]:
        ctx = dict(self.context or {})
        ctx["messages"] = list(self.messages)
        if self.restaurant_id:
            ctx["restaurant_id"] = self.restaurant_id
        return ctx


def _cart_from_order(db: Session, order: CustomerOrder | None) -> list[dict[str, Any]]:
    if order is None:
        return []
    lines = db.execute(
        select(CustomerOrderItem).where(CustomerOrderItem.order_id == order.id)
    ).scalars().all()
    cart: list[dict[str, Any]] = []
    for line in lines:
        cart.append(
            {
                "item_id": line.menu_item_id,
                "name": line.name_ar or line.name_en or "",
                "quantity": line.quantity,
                "price": line.unit_price_agorot / 100,
                "notes": None,
            }
        )
    return cart


def load_session(
    db: Session,
    customer_wa_number: str,
    *,
    restaurant_id: str | None = None,
) -> Session:
    phone = customer_wa_number.strip()
    cached: dict[str, Any] | None = None
    client = _redis_client()
    if client is not None:
        try:
            raw = client.get(_cache_key(phone))
            if raw:
                cached = json.loads(raw)
        except Exception:
            logger.debug("abuu_session_cache_read_failed phone=%s", phone, exc_info=True)

    customer = AbuuOrderDraftService.get_or_create_customer(db, phone)
    row = AbuuOrderDraftService.get_session(db, phone)
    context: dict[str, Any] = {}
    if cached and isinstance(cached.get("context"), dict):
        context = cached["context"]
    elif row is not None:
        try:
            loaded = json.loads(row.context_json or "{}")
            context = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            context = {}

    order: CustomerOrder | None = None
    active_order_id = row.active_order_id if row else None
    if active_order_id:
        order = db.get(CustomerOrder, active_order_id)
    step = row.step if row else "idle"
    from app.abuu.agent.session_reset import order_binds_restaurant

    resolved_restaurant = restaurant_id
    if order is not None and order.restaurant_id and order_binds_restaurant(db, order, context=context):
        resolved_restaurant = order.restaurant_id
    elif context.get("restaurant_selected") and context.get("restaurant_id"):
        resolved_restaurant = context.get("restaurant_id")
    elif order is not None and order.status in {"delivered", "cancelled"}:
        resolved_restaurant = None
        context.pop("restaurant_id", None)
        context.pop("restaurant_selected", None)
    elif not context.get("restaurant_selected"):
        resolved_restaurant = None
        context.pop("restaurant_id", None)

    messages = context.get("messages") or []
    if not isinstance(messages, list):
        messages = []

    session = Session(
        customer_wa_number=phone,
        restaurant_id=str(resolved_restaurant) if resolved_restaurant else None,
        messages=[m for m in messages if isinstance(m, dict)],
        cart=_cart_from_order(db, order),
        stage=step_to_stage(step if order and order.status == "confirmed" else step),
        language=customer.preferred_language or "ar",
        active_order_id=active_order_id,
        context={k: v for k, v in context.items() if k != "messages"},
        customer_id=customer.id,
    )
    if order is not None and order.status == "confirmed":
        session.stage = "done"
    return session


def save_session(db: Session, session: Session, *, message_id: str | None = None) -> None:
    customer = db.get(CustomerProfile, session.customer_id) if session.customer_id else None
    if customer is not None and session.language:
        customer.preferred_language = session.language
        db.add(customer)

    context = session.to_context_json()
    step = stage_to_step(session.stage)
    AbuuOrderDraftService.upsert_session(
        db,
        phone=session.customer_wa_number,
        step=step,
        context=context,
        active_order_id=session.active_order_id,
        message_id=message_id,
    )

    client = _redis_client()
    if client is not None:
        try:
            payload = json.dumps({"context": context, "stage": session.stage}, ensure_ascii=False)
            client.setex(_cache_key(session.customer_wa_number), timedelta(hours=24), payload)
        except Exception:
            logger.debug("abuu_session_cache_write_failed phone=%s", session.customer_wa_number, exc_info=True)


def clear_session(db: Session, customer_wa_number: str) -> None:
    phone = customer_wa_number.strip()
    AbuuOrderDraftService.clear_session(db, phone)
    client = _redis_client()
    if client is not None:
        try:
            client.delete(_cache_key(phone))
        except Exception:
            logger.debug("abuu_session_cache_clear_failed phone=%s", phone, exc_info=True)
