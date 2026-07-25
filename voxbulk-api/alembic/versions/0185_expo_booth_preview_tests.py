"""Expo booth preview test counter for pre-start mobile testing.

Revision ID: 0185_expo_booth_preview_tests
Revises: 0184_private_org_packages
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0185_expo_booth_preview_tests"
down_revision = "0184_private_org_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expo_booths",
        sa.Column("preview_tests_used", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("expo_booths", "preview_tests_used")
