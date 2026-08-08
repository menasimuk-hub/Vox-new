"""Add organisations.logo_tone for Smart Card / Feedback / Expo contrast plates."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0230_org_logo_tone"
down_revision = "0229_support_ticket_email_fingerprint"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if table not in sa.inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    if not _has_column("organisations", "logo_tone"):
        op.add_column("organisations", sa.Column("logo_tone", sa.String(length=16), nullable=True))


def downgrade() -> None:
    if _has_column("organisations", "logo_tone"):
        op.drop_column("organisations", "logo_tone")
