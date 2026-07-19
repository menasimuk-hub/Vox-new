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
    # MySQL (esp. older modes) rejects DEFAULT on TEXT/BLOB — add nullable, backfill, then NOT NULL.
    op.add_column(
        "site_seo_settings",
        sa.Column("marketing_pages_json", sa.Text(), nullable=True),
    )
    op.execute("UPDATE site_seo_settings SET marketing_pages_json = '{}' WHERE marketing_pages_json IS NULL")
    op.alter_column(
        "site_seo_settings",
        "marketing_pages_json",
        existing_type=sa.Text(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("site_seo_settings", "marketing_pages_json")
