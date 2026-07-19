"""0170 — SEO Control: editable marketing page meta JSON.

Revision ID: 0170_seo_marketing_pages
Revises: 0169_site_seo_control
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0170_seo_marketing_pages"
down_revision = "0169_site_seo_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_seo_settings",
        sa.Column("marketing_pages_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("site_seo_settings", "marketing_pages_json")
