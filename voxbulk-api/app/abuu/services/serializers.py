"""Serialize Abuu ORM rows to JSON-friendly dicts."""

from __future__ import annotations

from app.abuu.models.entities import (
    AbuuExternalEvent,
    AbuuNotification,
    CustomerAddress,
    CustomerOrder,
    CustomerOrderItem,
    CustomerProfile,
    DeliveryAssignment,
    Driver,
    OrderEvent,
    Restaurant,
    RestaurantMenuCategory,
    RestaurantMenuItem,
)
from app.abuu.services.abuu_menu_photo_storage_service import photo_url_for


def restaurant_to_dict(row: Restaurant) -> dict:
    return {
        "id": row.id,
        "name_en": row.name_en,
        "name_ar": row.name_ar,
        "status": row.status,
        "is_available": row.is_available,
        "delivery_radius_km": row.delivery_radius_km,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "address_text": row.address_text,
        "phone": row.phone,
        "login_email": row.login_email,
        "has_password": bool(row.password_hash),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def menu_category_to_dict(row: RestaurantMenuCategory) -> dict:
    return {
        "id": row.id,
        "restaurant_id": row.restaurant_id,
        "parent_category_id": row.parent_category_id,
        "name_en": row.name_en,
        "name_ar": row.name_ar,
        "sort_order": row.sort_order,
        "is_available": row.is_available,
    }


def menu_item_to_dict(row: RestaurantMenuItem) -> dict:
    return {
        "id": row.id,
        "category_id": row.category_id,
        "name_en": row.name_en,
        "name_ar": row.name_ar,
        "description_en": row.description_en,
        "description_ar": row.description_ar,
        "item_type": row.item_type,
        "price_agorot": row.price_agorot,
        "parent_menu_item_id": row.parent_menu_item_id,
        "photo_storage_key": row.photo_storage_key,
        "photo_url": photo_url_for(row.photo_storage_key),
        "is_available": row.is_available,
    }


def driver_to_dict(row: Driver) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "phone": row.phone,
        "status": row.status,
        "is_available": row.is_available,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "vehicle_info": row.vehicle_info,
        "login_email": row.login_email,
        "has_password": bool(row.password_hash),
    }


def customer_to_dict(row: CustomerProfile) -> dict:
    return {
        "id": row.id,
        "phone": row.phone,
        "name": row.name,
        "preferred_language": row.preferred_language,
        "likes_json": row.likes_json,
        "dislikes_json": row.dislikes_json,
        "order_count": row.order_count,
    }


def address_to_dict(row: CustomerAddress) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "label": row.label,
        "address_text": row.address_text,
        "latitude": row.latitude,
        "longitude": row.longitude,
        "source_message_id": row.source_message_id,
        "is_default": row.is_default,
    }


def order_to_dict(row: CustomerOrder, *, items: list | None = None, events: list | None = None) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "restaurant_id": row.restaurant_id,
        "status": row.status,
        "payment_status": row.payment_status,
        "total_agorot": row.total_agorot,
        "currency": row.currency,
        "delivery_address_id": row.delivery_address_id,
        "notes": row.notes,
        "draft_json": row.draft_json,
        "location_missing": getattr(row, "location_missing", False),
        "location_clarification_sent": getattr(row, "location_clarification_sent", False),
        "refund_ready": getattr(row, "refund_ready", False),
        "prep_delay_note": getattr(row, "prep_delay_note", None),
        "cancelled_reason": getattr(row, "cancelled_reason", None),
        "substitution_pending": getattr(row, "substitution_pending", False),
        "items": items,
        "events": events,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def order_item_to_dict(row: CustomerOrderItem) -> dict:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "menu_item_id": row.menu_item_id,
        "name_en": row.name_en,
        "name_ar": row.name_ar,
        "quantity": row.quantity,
        "unit_price_agorot": row.unit_price_agorot,
        "line_total_agorot": row.line_total_agorot,
        "unavailable": getattr(row, "unavailable", False),
        "substitution_status": getattr(row, "substitution_status", None),
    }


def assignment_to_dict(row: DeliveryAssignment) -> dict:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "driver_id": row.driver_id,
        "status": row.status,
        "assigned_at": row.assigned_at.isoformat() if row.assigned_at else None,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
        "timed_out_at": row.timed_out_at.isoformat() if row.timed_out_at else None,
        "picked_up_at": row.picked_up_at.isoformat() if row.picked_up_at else None,
        "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
        "failure_reason": row.failure_reason,
        "customer_notified_at": row.customer_notified_at.isoformat() if row.customer_notified_at else None,
    }


def event_to_dict(row: OrderEvent) -> dict:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "event_type": row.event_type,
        "payload_json": row.payload_json,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def notification_to_dict(row: AbuuNotification) -> dict:
    return {
        "id": row.id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "order_id": row.order_id,
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "payload_json": row.payload_json,
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def external_event_to_dict(row: AbuuExternalEvent) -> dict:
    return {
        "id": row.id,
        "source": row.source,
        "event_type": row.event_type,
        "idempotency_key": row.idempotency_key,
        "source_message_id": row.source_message_id,
        "order_id": row.order_id,
        "payload_hash": row.payload_hash,
        "status": row.status,
        "error_detail": row.error_detail,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
