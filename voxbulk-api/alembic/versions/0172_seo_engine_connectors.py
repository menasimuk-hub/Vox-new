"""0172 — SEO engine connectors, weekly auto-submit, keyword ideas.

Revision ID: 0172_seo_engine_connectors
Revises: 0171_marketing_faqs_replace_demo
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0172_seo_engine_connectors"
down_revision = "0171_marketing_faqs_replace_demo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_seo_settings", sa.Column("bing_api_key_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "site_seo_settings",
        sa.Column("bing_site_url", sa.String(300), nullable=False, server_default="https://voxbulk.com"),
    )
    op.add_column(
        "site_seo_settings",
        sa.Column("bing_connected", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("site_seo_settings", sa.Column("bing_last_submitted_at", sa.DateTime(), nullable=True))
    op.add_column("site_seo_settings", sa.Column("bing_last_error", sa.Text(), nullable=False, server_default=""))
    op.add_column("site_seo_settings", sa.Column("yandex_oauth_token_encrypted", sa.Text(), nullable=True))
    op.add_column("site_seo_settings", sa.Column("yandex_user_id", sa.String(64), nullable=False, server_default=""))
    op.add_column("site_seo_settings", sa.Column("yandex_host_id", sa.String(120), nullable=False, server_default=""))
    op.add_column(
        "site_seo_settings",
        sa.Column("yandex_connected", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("site_seo_settings", sa.Column("yandex_last_submitted_at", sa.DateTime(), nullable=True))
    op.add_column("site_seo_settings", sa.Column("yandex_last_error", sa.Text(), nullable=False, server_default=""))
    op.add_column(
        "site_seo_settings",
        sa.Column("auto_submit_weekly", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "site_seo_settings",
        sa.Column("auto_indexnow_on_publish", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column("site_seo_settings", sa.Column("engines_last_run_at", sa.DateTime(), nullable=True))
    op.add_column(
        "site_seo_settings",
        sa.Column("engines_last_result_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "site_seo_settings",
        sa.Column("keyword_ideas_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column("site_seo_settings", sa.Column("google_last_submit_error", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    for col in (
        "google_last_submit_error",
        "keyword_ideas_json",
        "engines_last_result_json",
        "engines_last_run_at",
        "auto_indexnow_on_publish",
        "auto_submit_weekly",
        "yandex_last_error",
        "yandex_last_submitted_at",
        "yandex_connected",
        "yandex_host_id",
        "yandex_user_id",
        "yandex_oauth_token_encrypted",
        "bing_last_error",
        "bing_last_submitted_at",
        "bing_connected",
        "bing_site_url",
        "bing_api_key_encrypted",
    ):
        op.drop_column("site_seo_settings", col)
