"""Abuu foundation tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_abuu_foundation"
down_revision = "0001_abuu_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "abuu_restaurants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=False),
        sa.Column("name_ar", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("delivery_radius_km", sa.Float(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("address_text", sa.String(length=512), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("login_email", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login_email"),
    )
    op.create_index("ix_abuu_restaurants_status", "abuu_restaurants", ["status"])

    op.create_table(
        "abuu_menu_categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("restaurant_id", sa.String(length=36), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=False),
        sa.Column("name_ar", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["restaurant_id"], ["abuu_restaurants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_menu_categories_restaurant_id", "abuu_menu_categories", ["restaurant_id"])

    op.create_table(
        "abuu_menu_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=False),
        sa.Column("name_ar", sa.String(length=255), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("description_ar", sa.Text(), nullable=True),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("price_agorot", sa.Integer(), nullable=False),
        sa.Column("parent_menu_item_id", sa.String(length=36), nullable=True),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["abuu_menu_categories.id"]),
        sa.ForeignKeyConstraint(["parent_menu_item_id"], ["abuu_menu_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_menu_items_category_id", "abuu_menu_items", ["category_id"])
    op.create_index("ix_abuu_menu_items_item_type", "abuu_menu_items", ["item_type"])

    op.create_table(
        "abuu_drivers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("vehicle_info", sa.String(length=255), nullable=True),
        sa.Column("login_email", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login_email"),
    )
    op.create_index("ix_abuu_drivers_status", "abuu_drivers", ["status"])

    op.create_table(
        "abuu_customers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("preferred_language", sa.String(length=8), nullable=False),
        sa.Column("likes_json", sa.Text(), nullable=True),
        sa.Column("dislikes_json", sa.Text(), nullable=True),
        sa.Column("order_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone", name="uq_abuu_customers_phone"),
    )
    op.create_index("ix_abuu_customers_phone", "abuu_customers", ["phone"])

    op.create_table(
        "abuu_customer_addresses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=True),
        sa.Column("address_text", sa.String(length=512), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["abuu_customers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_customer_addresses_customer_id", "abuu_customer_addresses", ["customer_id"])

    op.create_table(
        "abuu_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("restaurant_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payment_status", sa.String(length=32), nullable=False),
        sa.Column("total_agorot", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("delivery_address_id", sa.String(length=36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("draft_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["abuu_customers.id"]),
        sa.ForeignKeyConstraint(["restaurant_id"], ["abuu_restaurants.id"]),
        sa.ForeignKeyConstraint(["delivery_address_id"], ["abuu_customer_addresses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_orders_customer_id", "abuu_orders", ["customer_id"])
    op.create_index("ix_abuu_orders_restaurant_id", "abuu_orders", ["restaurant_id"])
    op.create_index("ix_abuu_orders_status", "abuu_orders", ["status"])
    op.create_index("ix_abuu_orders_payment_status", "abuu_orders", ["payment_status"])

    op.create_table(
        "abuu_order_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("menu_item_id", sa.String(length=36), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_agorot", sa.Integer(), nullable=False),
        sa.Column("line_total_agorot", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["menu_item_id"], ["abuu_menu_items.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["abuu_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_order_items_order_id", "abuu_order_items", ["order_id"])
    op.create_index("ix_abuu_order_items_menu_item_id", "abuu_order_items", ["menu_item_id"])

    op.create_table(
        "abuu_delivery_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("driver_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["driver_id"], ["abuu_drivers.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["abuu_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_abuu_delivery_assignments_order_id", "abuu_delivery_assignments", ["order_id"])
    op.create_index("ix_abuu_delivery_assignments_driver_id", "abuu_delivery_assignments", ["driver_id"])
    op.create_index("ix_abuu_delivery_assignments_status", "abuu_delivery_assignments", ["status"])

    op.create_table(
        "abuu_order_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["abuu_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_order_events_order_id", "abuu_order_events", ["order_id"])
    op.create_index("ix_abuu_order_events_event_type", "abuu_order_events", ["event_type"])

    op.create_table(
        "abuu_conversation_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_phone", sa.String(length=32), nullable=False),
        sa.Column("active_order_id", sa.String(length=36), nullable=True),
        sa.Column("step", sa.String(length=64), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("last_message_id", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["active_order_id"], ["abuu_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_phone"),
    )
    op.create_index("ix_abuu_conversation_sessions_customer_phone", "abuu_conversation_sessions", ["customer_phone"])

    op.create_table(
        "abuu_payments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("amount_agorot", sa.Integer(), nullable=False),
        sa.Column("confirmed_by", sa.String(length=255), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["abuu_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_abuu_payments_order_id", "abuu_payments", ["order_id"])
    op.create_index("ix_abuu_payments_status", "abuu_payments", ["status"])


def downgrade() -> None:
    op.drop_table("abuu_payments")
    op.drop_table("abuu_conversation_sessions")
    op.drop_table("abuu_order_events")
    op.drop_table("abuu_delivery_assignments")
    op.drop_table("abuu_order_items")
    op.drop_table("abuu_orders")
    op.drop_table("abuu_customer_addresses")
    op.drop_table("abuu_customers")
    op.drop_table("abuu_drivers")
    op.drop_table("abuu_menu_items")
    op.drop_table("abuu_menu_categories")
    op.drop_table("abuu_restaurants")
