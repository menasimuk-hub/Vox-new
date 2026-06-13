"""Customer memory helpers for Abuu WhatsApp ordering."""

from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerAddress, CustomerOrder, CustomerProfile, RestaurantMenuItem
from app.abuu.services.location_service import get_default_address


def first_name(full_name: str | None) -> str | None:
    cleaned = str(full_name or "").strip()
    if not cleaned:
        return None
    return cleaned.split()[0]


def parse_likes(customer: CustomerProfile) -> list[str]:
    try:
        data = json.loads(customer.likes_json or "[]")
        return [str(x).strip().lower() for x in data if str(x).strip()] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def parse_dislikes(customer: CustomerProfile) -> list[str]:
    try:
        data = json.loads(customer.dislikes_json or "[]")
        return [str(x).strip().lower() for x in data if str(x).strip()] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def remember_preference(customer: CustomerProfile, *, category: str) -> None:
    likes = parse_likes(customer)
    key = str(category or "").strip().lower()
    if not key or key in likes:
        return
    likes.append(key)
    customer.likes_json = json.dumps(likes[-10:])


def remember_disliked_item(customer: CustomerProfile, item: RestaurantMenuItem) -> None:
    dislikes = parse_dislikes(customer)
    label = str(item.name_en or item.name_ar or item.id).strip().lower()
    if not label or label in dislikes:
        return
    dislikes.append(label)
    customer.dislikes_json = json.dumps(dislikes[-20:])


def save_customer_name(customer: CustomerProfile, raw_name: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(raw_name or "").strip())
    if len(cleaned) > 80:
        cleaned = cleaned[:80].strip()
    customer.name = cleaned or customer.name
    return customer.name or ""


def apply_saved_address_to_order(db: Session, order: CustomerOrder, customer: CustomerProfile) -> CustomerAddress | None:
    if order.delivery_address_id:
        return db.get(CustomerAddress, order.delivery_address_id)
    default_address = get_default_address(db, customer.id)
    if default_address is None:
        return None
    order.delivery_address_id = default_address.id
    order.location_missing = False
    db.add(order)
    return default_address


def saved_address_summary(db: Session, customer: CustomerProfile) -> str | None:
    address = get_default_address(db, customer.id)
    if address is None:
        return None
    return str(address.address_text or "").strip() or None
