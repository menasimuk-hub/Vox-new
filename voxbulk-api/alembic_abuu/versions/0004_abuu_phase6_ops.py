"""Abuu Phase 6: menu subcategories, photos, location source, notifications, status migration."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_abuu_phase6_ops"
down_revision = "0003_abuu_seed_restaurants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("abuu_menu_categories") as batch_op:
        batch_op.add_column(sa.Column("parent_category_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_abuu_menu_categories_parent_category_id", ["parent_category_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_abuu_menu_categories_parent",
            "abuu_menu_categories",
            ["parent_category_id"],
            ["id"],
        )

    op.add_column("abuu_menu_items", sa.Column("photo_storage_key", sa.String(length=512), nullable=True))
    op.add_column("abuu_customer_addresses", sa.Column("source_message_id", sa.String(length=128), nullable=True))

    op.create_table(
        "abuu_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["abuu_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_notifications_target_type", "abuu_notifications", ["target_type"])
    op.create_index("ix_abuu_notifications_target_id", "abuu_notifications", ["target_id"])
    op.create_index("ix_abuu_notifications_order_id", "abuu_notifications", ["order_id"])
    op.create_index("ix_abuu_notifications_kind", "abuu_notifications", ["kind"])

    conn = op.get_bind()
    conn.execute(sa.text("UPDATE abuu_orders SET status = 'confirmed' WHERE status = 'pending_payment'"))
    conn.execute(
        sa.text(
            "UPDATE abuu_orders SET status = 'sent_to_restaurant' "
            "WHERE status IN ('paid', 'preparing')"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE abuu_orders SET status = 'assigned_to_driver' WHERE status = 'dispatched'"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE abuu_orders SET status = 'pending_payment' WHERE status = 'confirmed'"))
    conn.execute(
        sa.text(
            "UPDATE abuu_orders SET status = 'preparing' "
            "WHERE status IN ('sent_to_restaurant', 'paid')"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE abuu_orders SET status = 'dispatched' WHERE status = 'assigned_to_driver'"
        )
    )

    op.drop_index("ix_abuu_notifications_kind", table_name="abuu_notifications")
    op.drop_index("ix_abuu_notifications_order_id", table_name="abuu_notifications")
    op.drop_index("ix_abuu_notifications_target_id", table_name="abuu_notifications")
    op.drop_index("ix_abuu_notifications_target_type", table_name="abuu_notifications")
    op.drop_table("abuu_notifications")

    op.drop_column("abuu_customer_addresses", "source_message_id")
    op.drop_column("abuu_menu_items", "photo_storage_key")

    with op.batch_alter_table("abuu_menu_categories") as batch_op:
        batch_op.drop_constraint("fk_abuu_menu_categories_parent", type_="foreignkey")
        batch_op.drop_index("ix_abuu_menu_categories_parent_category_id")
        batch_op.drop_column("parent_category_id")
