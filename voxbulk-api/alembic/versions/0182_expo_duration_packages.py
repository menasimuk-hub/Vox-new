"""Expo packages: duration_days; booth activated_at / expires_at.

Revision ID: 0182_expo_duration_packages
Revises: 0181_expo_question_templates
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0182_expo_duration_packages"
down_revision = "0181_expo_question_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expo_packages",
        sa.Column("duration_days", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("expo_booths", sa.Column("activated_at", sa.DateTime(), nullable=True))
    op.add_column("expo_booths", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_expo_booths_expires_at", "expo_booths", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_expo_booths_expires_at", table_name="expo_booths")
    op.drop_column("expo_booths", "expires_at")
    op.drop_column("expo_booths", "activated_at")
    op.drop_column("expo_packages", "duration_days")
