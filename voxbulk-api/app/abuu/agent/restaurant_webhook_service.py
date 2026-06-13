"""Outbound webhook when an order is confirmed."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.abuu.models.entities import CustomerOrder
from app.abuu.services.serializers import order_to_dict
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def post_restaurant_webhook(order: CustomerOrder, *, extra: dict[str, Any] | None = None) -> bool:
    settings = get_settings()
    url = (settings.abuu_restaurant_webhook_url or "").strip()
    if not url:
        return False
    payload = {"event": "order_confirmed", "order": order_to_dict(order)}
    if extra:
        payload.update(extra)
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    "abuu_restaurant_webhook_failed order_id=%s status=%s",
                    order.id,
                    resp.status_code,
                )
                return False
        return True
    except Exception:
        logger.exception("abuu_restaurant_webhook_error order_id=%s", order.id)
        return False
