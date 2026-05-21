"""Plan lifecycle + unified product hub helpers.

Revision ID: 0054_plan_product_hub
Revises: 0053_sales_offer_email_template
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054_plan_product_hub"
down_revision = "0053_sales_offer_email_template"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _column_nullable(table: str, column: str) -> bool | None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for col in insp.get_columns(table):
        if col["name"] == column:
            return bool(col.get("nullable", True))
    return None


def upgrade() -> None:
    if not _has_column("plans", "is_active"):
        op.add_column("plans", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    if not _has_column("plans", "sort_order"):
        op.add_column("plans", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"))
    if not _has_column("plans", "updated_at"):
        op.add_column("plans", sa.Column("updated_at", sa.DateTime(), nullable=True))

    if _has_column("plans", "updated_at"):
        op.execute(sa.text("UPDATE plans SET updated_at = created_at WHERE updated_at IS NULL"))
        if _column_nullable("plans", "updated_at") is not False:
            op.alter_column(
                "plans",
                "updated_at",
                existing_type=sa.DateTime(),
                nullable=False,
            )

    if not _has_column("org_usage_periods", "overage_invoiced_pence"):
        op.add_column(
            "org_usage_periods",
            sa.Column("overage_invoiced_pence", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column("org_usage_periods", "last_overage_invoice_at"):
        op.add_column("org_usage_periods", sa.Column("last_overage_invoice_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if _has_column("org_usage_periods", "last_overage_invoice_at"):
        op.drop_column("org_usage_periods", "last_overage_invoice_at")
    if _has_column("org_usage_periods", "overage_invoiced_pence"):
        op.drop_column("org_usage_periods", "overage_invoiced_pence")
    if _has_column("plans", "updated_at"):
        op.drop_column("plans", "updated_at")
    if _has_column("plans", "sort_order"):
        op.drop_column("plans", "sort_order")
    if _has_column("plans", "is_active"):
        op.drop_column("plans", "is_active")
