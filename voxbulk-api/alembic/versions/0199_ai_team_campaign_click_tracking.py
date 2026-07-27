"""AI Team campaign recipient click tracking.

Revision ID: 0199_ai_team_campaign_click_tracking
Revises: 0198_ai_team_email_templates
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0199_ai_team_campaign_click_tracking"
down_revision = "0198_ai_team_email_templates"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_table("ai_team_campaign_recipients"):
        return
    if not _has_column("ai_team_campaign_recipients", "clicked_at"):
        op.add_column("ai_team_campaign_recipients", sa.Column("clicked_at", sa.DateTime(), nullable=True))
    if not _has_column("ai_team_campaign_recipients", "click_count"):
        op.add_column(
            "ai_team_campaign_recipients",
            sa.Column("click_count", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if _has_column("ai_team_campaign_recipients", "click_count"):
        op.drop_column("ai_team_campaign_recipients", "click_count")
    if _has_column("ai_team_campaign_recipients", "clicked_at"):
        op.drop_column("ai_team_campaign_recipients", "clicked_at")
