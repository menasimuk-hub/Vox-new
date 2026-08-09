"""Add marketing_consent + proof JSON on smart_card_leads.

Idempotent column add for MySQL/SQLite.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0236_smart_card_marketing_consent"
down_revision = "0235_smart_card_engagement_events"
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
    if not _has_table("smart_card_leads"):
        return
    if not _has_column("smart_card_leads", "marketing_consent"):
        op.add_column(
            "smart_card_leads",
            sa.Column("marketing_consent", sa.String(length=16), nullable=True),
        )
    if not _has_column("smart_card_leads", "marketing_consent_proof_json"):
        op.add_column(
            "smart_card_leads",
            sa.Column("marketing_consent_proof_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if not _has_table("smart_card_leads"):
        return
    if _has_column("smart_card_leads", "marketing_consent_proof_json"):
        op.drop_column("smart_card_leads", "marketing_consent_proof_json")
    if _has_column("smart_card_leads", "marketing_consent"):
        op.drop_column("smart_card_leads", "marketing_consent")
