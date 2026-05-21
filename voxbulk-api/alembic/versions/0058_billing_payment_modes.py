"""Billing payment modes — pending plan + service-order redirect flows.

Revision ID: 0058_billing_payment_modes
Revises: 0057_sales_automation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0058_billing_payment_modes"
down_revision = "0057_sales_automation"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if not _has_column("subscriptions", "pending_plan_id"):
        if is_sqlite:
            with op.batch_alter_table("subscriptions") as batch:
                batch.add_column(sa.Column("pending_plan_id", sa.String(length=36), nullable=True))
                batch.create_foreign_key(
                    "fk_subscriptions_pending_plan_id",
                    "plans",
                    ["pending_plan_id"],
                    ["id"],
                )
                batch.create_index("ix_subscriptions_pending_plan_id", ["pending_plan_id"])
        else:
            op.add_column(
                "subscriptions",
                sa.Column("pending_plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=True),
            )
            op.create_index("ix_subscriptions_pending_plan_id", "subscriptions", ["pending_plan_id"])

    if not _has_column("billing_redirect_flows", "service_order_id"):
        if is_sqlite:
            with op.batch_alter_table("billing_redirect_flows") as batch:
                batch.add_column(sa.Column("service_order_id", sa.String(length=36), nullable=True))
                batch.create_foreign_key(
                    "fk_billing_redirect_flows_service_order_id",
                    "service_orders",
                    ["service_order_id"],
                    ["id"],
                )
                batch.create_index("ix_billing_redirect_flows_service_order_id", ["service_order_id"])
        else:
            op.add_column(
                "billing_redirect_flows",
                sa.Column("service_order_id", sa.String(length=36), sa.ForeignKey("service_orders.id"), nullable=True),
            )
            op.create_index("ix_billing_redirect_flows_service_order_id", "billing_redirect_flows", ["service_order_id"])

    if is_sqlite:
        with op.batch_alter_table("billing_redirect_flows") as batch:
            batch.alter_column("plan_id", existing_type=sa.String(length=36), nullable=True)
    else:
        op.alter_column("billing_redirect_flows", "plan_id", existing_type=sa.String(length=36), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table("billing_redirect_flows") as batch:
            batch.alter_column("plan_id", existing_type=sa.String(length=36), nullable=False)
    else:
        op.alter_column("billing_redirect_flows", "plan_id", existing_type=sa.String(length=36), nullable=False)

    if _has_column("billing_redirect_flows", "service_order_id"):
        if is_sqlite:
            with op.batch_alter_table("billing_redirect_flows") as batch:
                batch.drop_index("ix_billing_redirect_flows_service_order_id")
                batch.drop_constraint("fk_billing_redirect_flows_service_order_id", type_="foreignkey")
                batch.drop_column("service_order_id")
        else:
            op.drop_index("ix_billing_redirect_flows_service_order_id", table_name="billing_redirect_flows")
            op.drop_column("billing_redirect_flows", "service_order_id")

    if _has_column("subscriptions", "pending_plan_id"):
        if is_sqlite:
            with op.batch_alter_table("subscriptions") as batch:
                batch.drop_index("ix_subscriptions_pending_plan_id")
                batch.drop_constraint("fk_subscriptions_pending_plan_id", type_="foreignkey")
                batch.drop_column("pending_plan_id")
        else:
            op.drop_index("ix_subscriptions_pending_plan_id", table_name="subscriptions")
            op.drop_column("subscriptions", "pending_plan_id")
