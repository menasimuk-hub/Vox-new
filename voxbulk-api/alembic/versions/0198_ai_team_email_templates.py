"""AI Team email templates + campaign.template_id.

Revision ID: 0198_ai_team_email_templates
Revises: 0197_ai_team_campaigns
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0198_ai_team_email_templates"
down_revision = "0197_ai_team_campaigns"
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
    if not _has_table("ai_team_email_templates"):
        op.create_table(
            "ai_team_email_templates",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("subject", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("body_text", sa.Text(), nullable=False),
            sa.Column("html_template", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if _has_table("ai_team_campaigns") and not _has_column("ai_team_campaigns", "template_id"):
        op.add_column("ai_team_campaigns", sa.Column("template_id", sa.String(length=36), nullable=True))
        op.create_index("ix_ai_team_campaigns_template_id", "ai_team_campaigns", ["template_id"])


def downgrade() -> None:
    if _has_column("ai_team_campaigns", "template_id"):
        op.drop_index("ix_ai_team_campaigns_template_id", table_name="ai_team_campaigns")
        op.drop_column("ai_team_campaigns", "template_id")
    if _has_table("ai_team_email_templates"):
        op.drop_table("ai_team_email_templates")
