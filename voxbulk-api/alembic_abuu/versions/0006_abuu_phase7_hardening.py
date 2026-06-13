"""Abuu Phase 7: idempotency, menu audit, driver safety, order exceptions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_abuu_phase7_hardening"
down_revision = "0005_abuu_seed_city"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("abuu_orders", sa.Column("location_missing", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("abuu_orders", sa.Column("location_clarification_sent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("abuu_orders", sa.Column("refund_ready", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("abuu_orders", sa.Column("prep_delay_note", sa.Text(), nullable=True))
    op.add_column("abuu_orders", sa.Column("cancelled_reason", sa.String(length=512), nullable=True))

    op.add_column("abuu_order_items", sa.Column("name_en", sa.String(length=255), nullable=True))
    op.add_column("abuu_order_items", sa.Column("name_ar", sa.String(length=255), nullable=True))
    op.add_column("abuu_order_items", sa.Column("item_type", sa.String(length=32), nullable=True))

    with op.batch_alter_table("abuu_delivery_assignments") as batch_op:
        batch_op.add_column(sa.Column("accepted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("rejected_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("timed_out_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("failure_reason", sa.String(length=512), nullable=True))

    op.create_table(
        "abuu_external_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("source_message_id", sa.String(length=128), nullable=True),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["abuu_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "idempotency_key", name="uq_abuu_external_events_source_key"),
    )
    op.create_index("ix_abuu_external_events_source", "abuu_external_events", ["source"])
    op.create_index("ix_abuu_external_events_event_type", "abuu_external_events", ["event_type"])
    op.create_index("ix_abuu_external_events_status", "abuu_external_events", ["status"])
    op.create_index("ix_abuu_external_events_order_id", "abuu_external_events", ["order_id"])

    op.create_table(
        "abuu_menu_audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("restaurant_id", sa.String(length=36), nullable=False),
        sa.Column("menu_item_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["menu_item_id"], ["abuu_menu_items.id"]),
        sa.ForeignKeyConstraint(["restaurant_id"], ["abuu_restaurants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_menu_audit_logs_restaurant_id", "abuu_menu_audit_logs", ["restaurant_id"])
    op.create_index("ix_abuu_menu_audit_logs_menu_item_id", "abuu_menu_audit_logs", ["menu_item_id"])

    op.create_table(
        "abuu_assignment_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=True),
        sa.Column("driver_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id"], ["abuu_delivery_assignments.id"]),
        sa.ForeignKeyConstraint(["driver_id"], ["abuu_drivers.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["abuu_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_assignment_attempts_order_id", "abuu_assignment_attempts", ["order_id"])

    with op.batch_alter_table("abuu_notifications") as batch_op:
        batch_op.create_unique_constraint(
            "uq_abuu_notifications_order_kind_target",
            ["order_id", "kind", "target_type", "target_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("abuu_notifications") as batch_op:
        batch_op.drop_constraint("uq_abuu_notifications_order_kind_target", type_="unique")

    op.drop_index("ix_abuu_assignment_attempts_order_id", table_name="abuu_assignment_attempts")
    op.drop_table("abuu_assignment_attempts")
    op.drop_index("ix_abuu_menu_audit_logs_menu_item_id", table_name="abuu_menu_audit_logs")
    op.drop_index("ix_abuu_menu_audit_logs_restaurant_id", table_name="abuu_menu_audit_logs")
    op.drop_table("abuu_menu_audit_logs")
    op.drop_index("ix_abuu_external_events_order_id", table_name="abuu_external_events")
    op.drop_index("ix_abuu_external_events_status", table_name="abuu_external_events")
    op.drop_index("ix_abuu_external_events_event_type", table_name="abuu_external_events")
    op.drop_index("ix_abuu_external_events_source", table_name="abuu_external_events")
    op.drop_table("abuu_external_events")

    with op.batch_alter_table("abuu_delivery_assignments") as batch_op:
        batch_op.drop_column("failure_reason")
        batch_op.drop_column("timed_out_at")
        batch_op.drop_column("rejected_at")
        batch_op.drop_column("accepted_at")

    op.drop_column("abuu_order_items", "item_type")
    op.drop_column("abuu_order_items", "name_ar")
    op.drop_column("abuu_order_items", "name_en")
    op.drop_column("abuu_orders", "cancelled_reason")
    op.drop_column("abuu_orders", "prep_delay_note")
    op.drop_column("abuu_orders", "refund_ready")
    op.drop_column("abuu_orders", "location_clarification_sent")
    op.drop_column("abuu_orders", "location_missing")
