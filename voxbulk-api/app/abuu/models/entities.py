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
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    city_slug: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class RestaurantMenuCategory(AbuuBase, AbuuTimestampMixin, AbuuSoftDeleteMixin):
    __tablename__ = "abuu_menu_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    restaurant_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_restaurants.id"), nullable=False, index=True)
    parent_category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_menu_categories.id"), nullable=True, index=True)
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
    item_type: Mapped[str] = mapped_column(String(32), nullable=False, default="meat", index=True)
    price_agorot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_menu_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_menu_items.id"), nullable=True)
    photo_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AbuuMenuAuditLog(AbuuBase):
    __tablename__ = "abuu_menu_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    restaurant_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_restaurants.id"), nullable=False, index=True)
    menu_item_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_menu_items.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


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
    source_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
    location_missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    location_clarification_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    refund_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prep_delay_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    substitution_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CustomerOrderItem(AbuuBase, AbuuTimestampMixin):
    __tablename__ = "abuu_order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=False, index=True)
    menu_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_menu_items.id"), nullable=False, index=True)
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_agorot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_total_agorot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unavailable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unavailable_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    substitution_status: Mapped[str | None] = mapped_column(String(32), nullable=True)


class DeliveryAssignment(AbuuBase, AbuuTimestampMixin):
    __tablename__ = "abuu_delivery_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=False, unique=True, index=True)
    driver_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_drivers.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unassigned", index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    timed_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    customer_notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AbuuAssignmentAttempt(AbuuBase):
    __tablename__ = "abuu_assignment_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=False, index=True)
    assignment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_delivery_assignments.id"), nullable=True, index=True)
    driver_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_drivers.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class OrderEvent(AbuuBase):
    __tablename__ = "abuu_order_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AbuuNotification(AbuuBase):
    __tablename__ = "abuu_notifications"
    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "kind",
            "target_type",
            "target_id",
            name="uq_abuu_notifications_order_kind_target",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AbuuExternalEvent(AbuuBase):
    __tablename__ = "abuu_external_events"
    __table_args__ = (
        UniqueConstraint("source", "idempotency_key", name="uq_abuu_external_events_source_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_orders.id"), nullable=True, index=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processed", index=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AbuuInboundMessage(AbuuBase):
    __tablename__ = "abuu_inbound_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    customer_phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("abuu_customers.id"), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    message_type: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_media_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    voice_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    voice_storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
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


class AbuuAgentSettings(AbuuBase, AbuuTimestampMixin):
    __tablename__ = "abuu_agent_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    business_name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_name_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opening_hours_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_hours_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_delivery_radius_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    default_prep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_min_order_agorot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_delivery_fee_agorot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_methods_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_policy_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_policy_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_policy_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_policy_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    allergen_disclaimer_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    allergen_disclaimer_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_rules_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_rules_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    greeting_template_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    greeting_template_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    holiday_closures_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class AbuuRestaurantSettings(AbuuBase, AbuuTimestampMixin):
    __tablename__ = "abuu_restaurant_settings"
    __table_args__ = (UniqueConstraint("restaurant_id", name="uq_abuu_restaurant_settings_restaurant"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    restaurant_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_restaurants.id"), nullable=False, index=True)
    notes_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_hours_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_hours_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_radius_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    prep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_order_agorot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_fee_agorot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_methods_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_policy_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_policy_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_policy_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_policy_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    allergen_disclaimer_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    allergen_disclaimer_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_rules_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_rules_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    greeting_template_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    greeting_template_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    holiday_closures_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class RestaurantPromoOffer(AbuuBase, AbuuTimestampMixin, AbuuSoftDeleteMixin):
    __tablename__ = "abuu_restaurant_offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    restaurant_id: Mapped[str] = mapped_column(String(36), ForeignKey("abuu_restaurants.id"), nullable=False, index=True)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)
    title_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_price_agorot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    original_price_agorot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AbuuWaSnapshot(AbuuBase):
    __tablename__ = "abuu_wa_snapshots"
    __table_args__ = (UniqueConstraint("scope", "kind", "lang", name="uq_abuu_wa_snapshots_scope_kind_lang"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    scope: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    lang: Mapped[str] = mapped_column(String(8), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class AbuuMarketAgent(AbuuBase, AbuuTimestampMixin):
    __tablename__ = "abuu_market_agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    country_code: Mapped[str] = mapped_column(String(8), nullable=False)
    city_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    dialect_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="deepseek")
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False, default="deepseek-chat")
    pilot_restaurant_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
