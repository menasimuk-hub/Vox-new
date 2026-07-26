"""Merge alembic heads: expo categories + unified promo redesign.

Revision ID: 0193_merge_expo_promo_heads
Revises: 0192_expo_categories_reps, 0192_unified_promo_redesign
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "0193_merge_expo_promo_heads"
down_revision = ("0192_expo_categories_reps", "0192_unified_promo_redesign")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
