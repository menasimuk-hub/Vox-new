"""AI Team Apify scrape + SMTP delivery provider settings.

Revision ID: 0194_ai_team_apify_smtp
Revises: 0193_merge_expo_promo_heads
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0194_ai_team_apify_smtp"
down_revision = "0193_merge_expo_promo_heads"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if not _has_column("ai_team_settings", "email_delivery_provider"):
        op.add_column(
            "ai_team_settings",
            sa.Column("email_delivery_provider", sa.String(length=16), nullable=False, server_default="smtp"),
        )
    if not _has_column("ai_team_settings", "apify_token_enc"):
        op.add_column("ai_team_settings", sa.Column("apify_token_enc", sa.Text(), nullable=True))
    if not _has_column("ai_team_settings", "apify_exhibitor_actor_id"):
        op.add_column(
            "ai_team_settings",
            sa.Column("apify_exhibitor_actor_id", sa.String(length=255), nullable=False, server_default=""),
        )
    if not _has_column("ai_team_settings", "apify_contact_actor_id"):
        op.add_column(
            "ai_team_settings",
            sa.Column("apify_contact_actor_id", sa.String(length=255), nullable=False, server_default=""),
        )

    if not _has_table("ai_team_apify_runs"):
        op.create_table(
            "ai_team_apify_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("apify_run_id", sa.String(length=128), nullable=True),
            sa.Column("actor_id", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("expo_url", sa.String(length=1000), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="READY"),
            sa.Column("dataset_id", sa.String(length=128), nullable=True),
            sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stats_json", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_ai_team_apify_runs_apify_run_id", "ai_team_apify_runs", ["apify_run_id"])
        op.create_index("ix_ai_team_apify_runs_status", "ai_team_apify_runs", ["status"])


def downgrade() -> None:
    if _has_table("ai_team_apify_runs"):
        op.drop_index("ix_ai_team_apify_runs_status", table_name="ai_team_apify_runs")
        op.drop_index("ix_ai_team_apify_runs_apify_run_id", table_name="ai_team_apify_runs")
        op.drop_table("ai_team_apify_runs")
    for col in ("apify_contact_actor_id", "apify_exhibitor_actor_id", "apify_token_enc", "email_delivery_provider"):
        if _has_column("ai_team_settings", col):
            op.drop_column("ai_team_settings", col)
