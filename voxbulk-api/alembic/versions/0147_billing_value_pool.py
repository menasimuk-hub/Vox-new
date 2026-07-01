"""Billing value pool — monthly allowance tracked in minor currency units."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0147_billing_value_pool"
down_revision = "0146_agent_accent_region_gender"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "org_usage_periods",
        sa.Column("allowance_value_included_minor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "org_usage_periods",
        sa.Column("allowance_value_used_minor", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("org_usage_periods", "allowance_value_used_minor")
    op.drop_column("org_usage_periods", "allowance_value_included_minor")
