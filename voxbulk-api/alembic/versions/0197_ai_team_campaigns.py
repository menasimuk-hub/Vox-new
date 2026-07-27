"""AI Team campaigns + recipients for bulk outreach.

Revision ID: 0197_ai_team_campaigns
Revises: 0196_ai_team_apify_user_id
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0197_ai_team_campaigns"
down_revision = "0196_ai_team_apify_user_id"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("ai_team_campaigns"):
        op.create_table(
            "ai_team_campaigns",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("subject", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("body_text", sa.Text(), nullable=False),
            sa.Column("html_template", sa.Text(), nullable=True),
            sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("opened_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("replied_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_ai_team_campaigns_status", "ai_team_campaigns", ["status"])

    if not _has_table("ai_team_campaign_recipients"):
        op.create_table(
            "ai_team_campaign_recipients",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("campaign_id", sa.String(length=36), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("first_name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("last_name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("company_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("job_title", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("sector", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("country_code", sa.String(length=8), nullable=False, server_default="GB"),
            sa.Column("promo_code", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("provider_message_id", sa.String(length=128), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("opened_at", sa.DateTime(), nullable=True),
            sa.Column("replied_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_ai_team_campaign_recipients_campaign_id", "ai_team_campaign_recipients", ["campaign_id"])
        op.create_index("ix_ai_team_campaign_recipients_email", "ai_team_campaign_recipients", ["email"])
        op.create_index("ix_ai_team_campaign_recipients_status", "ai_team_campaign_recipients", ["status"])


def downgrade() -> None:
    if _has_table("ai_team_campaign_recipients"):
        op.drop_table("ai_team_campaign_recipients")
    if _has_table("ai_team_campaigns"):
        op.drop_table("ai_team_campaigns")
