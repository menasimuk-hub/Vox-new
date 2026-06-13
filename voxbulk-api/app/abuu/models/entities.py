from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.abuu.models.base import AbuuSoftDeleteMixin, AbuuTimestampMixin, new_uuid
from app.core.abuu_database import AbuuBase


class Restaurant(AbuuBase, AbuuTimestampMixin, AbuuSoftDeleteMixin):
    __tablename__ = "abuu_restaurants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    delivery_radius_km: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    address_text: Mapped[str | None] = mapped_column(String(512), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    login_email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)


class RestaurantMenuCategory(AbuuBase, AbuuTimestampMixin, AbuuSoftDeleteMixin):
    __tablename__ = "abuu_menu_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    restaurant_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_restaurants.id"), nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RestaurantMenuItem(AbuuBase, AbuuTimestampMixin, AbuuSoftDeleteMixin):
    __tablename__ = "abuu_menu_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    category_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_menu_categories.id"), nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False, default="food", index=True)
    price_agorot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_menu_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_menu_items.id"), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Driver(AbuuBase, AbuuTimestampMixin, AbuuSoftDeleteMixin):
    __tablename__ = "abuu_drivers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    vehicle_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    login_email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CustomerProfile(AbuuBase, AbuuTimestampMixin, AbuuSoftDeleteMixin):
    __tablename__ = "abuu_customers"
    __table_args__ = (UniqueConstraint("phone", name="uq_abuu_customers_phone"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(8), nullable=False, default="ar")
    likes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    dislikes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CustomerAddress(AbuuBase, AbuuTimestampMixin, AbuuSoftDeleteMixin):
    __tablename__ = "abuu_customer_addresses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_customers.id"), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address_text: Mapped[str] = mapped_column(String(512), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CustomerOrder(AbuuBase, AbuuTimestampMixin, AbuuSoftDeleteMixin):
    __tablename__ = "abuu_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    customer_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_customers.id"), nullable=False, index=True)
    restaurant_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_restaurants.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unpaid", index=True)
    total_agorot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="ILS")
    delivery_address_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_customer_addresses.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class CustomerOrderItem(AbuuBase, AbuuTimestampMixin):
    __tablename__ = "abuu_order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=False, index=True)
    menu_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_menu_items.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_agorot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_total_agorot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DeliveryAssignment(AbuuBase, AbuuTimestampMixin):
    __tablename__ = "abuu_delivery_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=False, unique=True, index=True)
    driver_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_drivers.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unassigned", index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OrderEvent(AbuuBase):
    __tablename__ = "abuu_order_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AbuuConversationSession(AbuuBase, AbuuTimestampMixin):
    __tablename__ = "abuu_conversation_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    customer_phone: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    active_order_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=True)
    step: Mapped[str] = mapped_column(String(64), nullable=False, default="idle")
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AbuuPayment(AbuuBase, AbuuTimestampMixin):
    __tablename__ = "abuu_payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_manual", index=True)
    amount_agorot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
