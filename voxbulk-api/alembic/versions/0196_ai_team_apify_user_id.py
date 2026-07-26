"""Add ai_team_settings.apify_user_id for Apify account user id.

Revision ID: 0196_ai_team_apify_user_id
Revises: 0195_ai_team_apify_stats_mediumtext
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0196_ai_team_apify_user_id"
down_revision = "0195_ai_team_apify_stats_mediumtext"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("ai_team_settings", "apify_user_id"):
        op.add_column(
            "ai_team_settings",
            sa.Column("apify_user_id", sa.String(length=128), nullable=False, server_default=""),
        )


def downgrade() -> None:
    if _has_column("ai_team_settings", "apify_user_id"):
        op.drop_column("ai_team_settings", "apify_user_id")
