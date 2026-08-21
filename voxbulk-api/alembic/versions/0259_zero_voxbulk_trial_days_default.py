"""0259 — Zero trial_days_default on core voxbulk plans (Interview / WA Survey).

Smart Card keeps its own trial_days_default (30). Core packages no longer
auto-apply a free trial; only a pending promo of type trial_days may grant one.

Revision ID: 0259_zero_voxbulk_trial_days_default
Revises: 0258_membership_role_null_to_member
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0259_zero_voxbulk_trial_days_default"
down_revision = "0258_membership_role_null_to_member"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE plans
            SET trial_days_default = 0
            WHERE LOWER(TRIM(COALESCE(service_kind, ''))) = 'voxbulk'
            """
        )
    )


def downgrade() -> None:
    # Cannot restore previous per-plan values; leave at 0.
    pass
