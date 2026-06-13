"""Delivery location helpers for Abuu."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerAddress, CustomerOrder, CustomerProfile, Restaurant

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_USER_AGENT = "VoxBulk-Abuu/1.0"


@dataclass(frozen=True)
class DeliveryLocation:
    latitude: float | None
    longitude: float | None
    address_text: str


@dataclass(frozen=True)
class NearestRestaurant:
    restaurant: Restaurant
    distance_km: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(min(1.0, math.sqrt(a)))


def reverse_geocode(lat: float, lng: float) -> str:
    fallback = f"{lat:.5f}, {lng:.5f}"
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(
                NOMINATIM_URL,
                params={"lat": lat, "lon": lng, "format": "json"},
                headers={"User-Agent": NOMINATIM_USER_AGENT},
            )
            if resp.status_code == 200:
                data = resp.json()
                display = str(data.get("display_name") or "").strip()
                if display:
                    return display
    except Exception:
        logger.warning("abuu_nominatim_failed lat=%s lng=%s", lat, lng, exc_info=True)
    return fallback


def _active_restaurants(db: Session) -> list[Restaurant]:
    return list(
        db.execute(
            select(Restaurant).where(
                Restaurant.is_deleted.is_(False),
                Restaurant.is_available.is_(True),
                Restaurant.status == "active",
            )
        ).scalars().all()
    )


def find_nearest_restaurants(
    db: Session,
    *,
    lat: float,
    lng: float,
    limit: int = 5,
) -> list[NearestRestaurant]:
    ranked: list[NearestRestaurant] = []
    for restaurant in _active_restaurants(db):
        if restaurant.latitude is None or restaurant.longitude is None:
            continue
        distance = haversine_km(lat, lng, restaurant.latitude, restaurant.longitude)
        ranked.append(NearestRestaurant(restaurant=restaurant, distance_km=distance))
    ranked.sort(key=lambda row: row.distance_km)
    return ranked[: max(1, limit)]


def validate_delivery_radius(
    restaurant: Restaurant,
    *,
    lat: float,
    lng: float,
) -> tuple[bool, float]:
    if restaurant.latitude is None or restaurant.longitude is None:
        return True, 0.0
    distance = haversine_km(lat, lng, restaurant.latitude, restaurant.longitude)
    return distance <= float(restaurant.delivery_radius_km or 0), distance


def get_default_address(db: Session, customer_id: str) -> CustomerAddress | None:
    return db.execute(
        select(CustomerAddress).where(
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.is_deleted.is_(False),
            CustomerAddress.is_default.is_(True),
        )
    ).scalars().first()


def attach_default_address_if_present(db: Session, order: CustomerOrder, customer: CustomerProfile) -> bool:
    if order.delivery_address_id:
        return True
    default_address = get_default_address(db, customer.id)
    if default_address is None:
        logger.warning(
            "abuu_missing_delivery_location order_id=%s customer_id=%s",
            order.id,
            customer.id,
        )
        return False
    order.delivery_address_id = default_address.id
    db.add(order)
    return True


def save_customer_address(
    db: Session,
    *,
    customer_id: str,
    address_text: str,
    latitude: float | None = None,
    longitude: float | None = None,
    label: str | None = "delivery",
    is_default: bool = True,
    source_message_id: str | None = None,
) -> CustomerAddress:
    if is_default:
        for row in db.execute(
            select(CustomerAddress).where(
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.is_deleted.is_(False),
            )
        ).scalars().all():
            row.is_default = False
            db.add(row)

    if latitude is not None and longitude is not None and not address_text.strip():
        address_text = reverse_geocode(latitude, longitude)

    row = CustomerAddress(
        customer_id=customer_id,
        label=label,
        address_text=address_text.strip(),
        latitude=latitude,
        longitude=longitude,
        source_message_id=source_message_id,
        is_default=is_default,
    )
    db.add(row)
    db.flush()
    return row


def _extract_location_block(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if any(key in value for key in ("latitude", "longitude", "lat", "lng")):
        return value
    for key in ("location", "address", "whatsapp_message", "body"):
        nested = _extract_location_block(value.get(key))
        if nested is not None:
            return nested
    return None


def parse_whatsapp_location(record: dict[str, Any] | None) -> DeliveryLocation | None:
    if not record:
        return None

    message_type = str(record.get("type") or "").lower()
    whatsapp_message = record.get("whatsapp_message")
    if isinstance(whatsapp_message, dict):
        message_type = str(whatsapp_message.get("type") or message_type).lower()

    if message_type != "location":
        block = _extract_location_block(record)
        if block is None:
            return None
    else:
        block = _extract_location_block(record) or record

    if block is None:
        return None

    lat_raw = block.get("latitude", block.get("lat"))
    lng_raw = block.get("longitude", block.get("lng", block.get("lon")))
    try:
        lat = float(lat_raw)
        lng = float(lng_raw)
    except (TypeError, ValueError):
        return None

    name = str(block.get("name") or "").strip()
    address = str(block.get("address") or block.get("address_text") or "").strip()
    address_text = address or name or reverse_geocode(lat, lng)
    return DeliveryLocation(latitude=lat, longitude=lng, address_text=address_text)
