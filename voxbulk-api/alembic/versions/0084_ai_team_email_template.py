"""Add HTML email template column for AI Team."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0084_ai_team_email_template"
down_revision = "0083_ai_team_sales"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("ai_team_settings", "email_html_template"):
        op.add_column("ai_team_settings", sa.Column("email_html_template", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("ai_team_settings", "email_html_template"):
        op.drop_column("ai_team_settings", "email_html_template")
