"""Lead sales calling hours settings.

Revision ID: 0043_lead_sales_calling_hours
Revises: 0042_lead_sales_outcomes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_lead_sales_calling_hours"
down_revision = "0042_lead_sales_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lead_sales_settings", sa.Column("calling_hour_start", sa.Integer(), nullable=False, server_default="9"))
    op.add_column("lead_sales_settings", sa.Column("calling_hour_end", sa.Integer(), nullable=False, server_default="18"))
    op.add_column("lead_sales_settings", sa.Column("calling_days", sa.String(length=32), nullable=False, server_default="1,2,3,4,5"))


def downgrade() -> None:
    op.drop_column("lead_sales_settings", "calling_days")
    op.drop_column("lead_sales_settings", "calling_hour_end")
    op.drop_column("lead_sales_settings", "calling_hour_start")
