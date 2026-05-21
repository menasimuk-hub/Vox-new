"""Onboarding auto-approve setting for promo signups.

Revision ID: 0055_onboarding_auto_approve_setting
Revises: 0054_plan_product_hub
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055_onboarding_auto_approve_setting"
down_revision = "0054_plan_product_hub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "onboarding_settings" not in insp.get_table_names():
        op.create_table(
            "onboarding_settings",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("auto_approve_promo_signups", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.execute(
            sa.text(
                "INSERT INTO onboarding_settings (id, auto_approve_promo_signups, updated_at) "
                "VALUES ('default', 1, CURRENT_TIMESTAMP)"
            )
        )


def downgrade() -> None:
    op.drop_table("onboarding_settings")
