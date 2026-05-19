"""organisation suspended flag and profile notes

Revision ID: 0016_org_suspended_profile_notes
Revises: 0015_add_onboarding_requests
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_org_suspended_profile_notes"
down_revision = "0015_add_onboarding_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organisations", sa.Column("is_suspended", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("organisations", sa.Column("profile_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("organisations", "profile_notes")
    op.drop_column("organisations", "is_suspended")
