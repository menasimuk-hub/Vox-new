"""0168 — site blog & news items for marketing site + admin CMS.

Revision ID: 0168_site_blog_news
Revises: 0167_feedback_bilingual_voice
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0168_site_blog_news"
down_revision = "0167_feedback_bilingual_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_blog_news_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="General"),
        sa.Column("author", sa.String(length=120), nullable=False, server_default="VoxBulk"),
        sa.Column("author_role", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("body_mode", sa.String(length=16), nullable=False, server_default="text"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Date(), nullable=False),
        sa.Column("read_mins", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_site_blog_news_items_kind", "site_blog_news_items", ["kind"])
    op.create_index("ix_site_blog_news_items_slug", "site_blog_news_items", ["slug"])
    op.create_index(
        "uq_site_blog_news_kind_slug",
        "site_blog_news_items",
        ["kind", "slug"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_site_blog_news_kind_slug", table_name="site_blog_news_items")
    op.drop_index("ix_site_blog_news_items_slug", table_name="site_blog_news_items")
    op.drop_index("ix_site_blog_news_items_kind", table_name="site_blog_news_items")
    op.drop_table("site_blog_news_items")
