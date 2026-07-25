"""Add expo_question_templates for Admin Expo WA tab (local session prompts).

Revision ID: 0181_expo_question_templates
Revises: 0180_expo_foundation
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0181_expo_question_templates"
down_revision = "0180_expo_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expo_question_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("question_key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("matches_products", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expo_question_templates_question_key", "expo_question_templates", ["question_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_expo_question_templates_question_key", table_name="expo_question_templates")
    op.drop_table("expo_question_templates")
