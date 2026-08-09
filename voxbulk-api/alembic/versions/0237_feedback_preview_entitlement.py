"""Customer Feedback preview tests + transparent QR on locations.

Idempotent column adds for MySQL/SQLite.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0237_feedback_preview_entitlement"
down_revision = "0236_smart_card_marketing_consent"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in sa.inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    if _has_table("organisations") and not _has_column("organisations", "feedback_preview_tests_used"):
        op.add_column(
            "organisations",
            sa.Column("feedback_preview_tests_used", sa.Integer(), nullable=False, server_default="0"),
        )
    if _has_table("feedback_locations") and not _has_column("feedback_locations", "qr_transparent"):
        op.add_column(
            "feedback_locations",
            sa.Column("qr_transparent", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    if _has_column("feedback_locations", "qr_transparent"):
        op.drop_column("feedback_locations", "qr_transparent")
    if _has_column("organisations", "feedback_preview_tests_used"):
        op.drop_column("organisations", "feedback_preview_tests_used")
