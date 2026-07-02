"""Org billing payment provider override (gocardless | airwallex | stripe)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0148_org_billing_payment_provider"
down_revision = "0147_billing_value_pool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("billing_payment_provider", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organisations", "billing_payment_provider")
