"""Sales rep payout details, commission types, and payout invoices.

Revision ID: 0188_sales_payout_invoices
Revises: 0187_sales_rep_kind_commission_pct
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0188_sales_payout_invoices"
down_revision = "0187_sales_rep_kind_commission_pct"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales_reps", sa.Column("mobile", sa.String(length=40), nullable=True))
    op.add_column(
        "sales_reps",
        sa.Column("commission_type", sa.String(length=24), nullable=False, server_default="month2"),
    )
    op.add_column(
        "sales_reps",
        sa.Column("commission_fixed_minor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("sales_reps", sa.Column("payout_method", sa.String(length=16), nullable=True))
    op.add_column("sales_reps", sa.Column("bank_holder_name", sa.String(length=200), nullable=True))
    op.add_column("sales_reps", sa.Column("bank_name", sa.String(length=120), nullable=True))
    op.add_column("sales_reps", sa.Column("bank_sort_code", sa.String(length=16), nullable=True))
    op.add_column("sales_reps", sa.Column("bank_account_number", sa.String(length=40), nullable=True))
    op.add_column("sales_reps", sa.Column("bank_address", sa.String(length=255), nullable=True))
    op.add_column("sales_reps", sa.Column("paypal_email", sa.String(length=320), nullable=True))

    # Backfill: partners use percent-on-pay; salesmen keep month2.
    op.execute(
        "UPDATE sales_reps SET commission_type = 'percent' WHERE kind = 'partner_channel'"
    )

    op.create_table(
        "sales_payout_invoices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sales_rep_id", sa.String(length=36), sa.ForeignKey("sales_reps.id"), nullable=False),
        sa.Column("invoice_number", sa.String(length=40), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="GBP"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="submitted"),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("payout_snapshot_json", sa.Text(), nullable=True),
        sa.Column("reject_reason", sa.String(length=500), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by_admin_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sales_payout_invoices_sales_rep_id", "sales_payout_invoices", ["sales_rep_id"])
    op.create_index("ix_sales_payout_invoices_invoice_number", "sales_payout_invoices", ["invoice_number"], unique=True)
    op.create_index("ix_sales_payout_invoices_status", "sales_payout_invoices", ["status"])

    op.add_column(
        "sales_commissions",
        sa.Column("payout_invoice_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_sales_commissions_payout_invoice_id", "sales_commissions", ["payout_invoice_id"])
    op.create_foreign_key(
        "fk_sales_commissions_payout_invoice_id",
        "sales_commissions",
        "sales_payout_invoices",
        ["payout_invoice_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_sales_commissions_payout_invoice_id", "sales_commissions", type_="foreignkey")
    op.drop_index("ix_sales_commissions_payout_invoice_id", table_name="sales_commissions")
    op.drop_column("sales_commissions", "payout_invoice_id")

    op.drop_index("ix_sales_payout_invoices_status", table_name="sales_payout_invoices")
    op.drop_index("ix_sales_payout_invoices_invoice_number", table_name="sales_payout_invoices")
    op.drop_index("ix_sales_payout_invoices_sales_rep_id", table_name="sales_payout_invoices")
    op.drop_table("sales_payout_invoices")

    for col in (
        "paypal_email",
        "bank_address",
        "bank_account_number",
        "bank_sort_code",
        "bank_name",
        "bank_holder_name",
        "payout_method",
        "commission_fixed_minor",
        "commission_type",
        "mobile",
    ):
        op.drop_column("sales_reps", col)
