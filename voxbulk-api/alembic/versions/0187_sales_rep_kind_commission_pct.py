"""Sales rep kind, company_name, and commission_pct for partner channel.

Revision ID: 0187_sales_rep_kind_commission_pct
Revises: 0186_expo_booth_payment_status
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0187_sales_rep_kind_commission_pct"
down_revision = "0186_expo_booth_payment_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales_reps", sa.Column("company_name", sa.String(length=200), nullable=True))
    op.add_column(
        "sales_reps",
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="salesman"),
    )
    op.add_column(
        "sales_reps",
        sa.Column("commission_pct", sa.Numeric(5, 2), nullable=False, server_default="15.00"),
    )
    op.create_index("ix_sales_reps_kind", "sales_reps", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sales_reps_kind", table_name="sales_reps")
    op.drop_column("sales_reps", "commission_pct")
    op.drop_column("sales_reps", "kind")
    op.drop_column("sales_reps", "company_name")
