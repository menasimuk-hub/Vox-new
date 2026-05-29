"""Add per_min_pence (bundle calc rate) separate from overage_per_min_pence (extra min)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0075_plan_per_min_split"
down_revision = "0074_voxbulk_pricing_model"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_column("plans", "per_min_pence"):
        op.add_column("plans", sa.Column("per_min_pence", sa.Integer(), nullable=False, server_default="0"))
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE plans SET per_min_pence = overage_per_min_pence WHERE (per_min_pence IS NULL OR per_min_pence = 0) AND overage_per_min_pence > 0"
        )
    )


def downgrade() -> None:
    if _has_column("plans", "per_min_pence"):
        op.drop_column("plans", "per_min_pence")
