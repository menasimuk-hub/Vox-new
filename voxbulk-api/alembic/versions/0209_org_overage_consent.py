"""Org overage consent timestamp + default allow_overage False for new orgs.

Revision ID: 0209_org_overage_consent
Revises: 0208_wallet_tx_provider_ref_unique
Create Date: 2026-07-29

No backfill: existing organisations keep their current allow_overage values.
Only the column server_default changes for newly inserted rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0209_org_overage_consent"
down_revision = "0208_wallet_tx_provider_ref_unique"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = sa.inspect(bind).get_columns(table)
    return any(c["name"] == column for c in cols)


def upgrade() -> None:
    if not _has_column("organisations", "overage_consent_accepted_at"):
        op.add_column(
            "organisations",
            sa.Column("overage_consent_accepted_at", sa.DateTime(), nullable=True),
        )
    # New inserts default to False; do not UPDATE existing rows.
    op.alter_column(
        "organisations",
        "allow_overage",
        existing_type=sa.Boolean(),
        server_default=sa.text("0"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "organisations",
        "allow_overage",
        existing_type=sa.Boolean(),
        server_default=sa.text("1"),
        existing_nullable=False,
    )
    if _has_column("organisations", "overage_consent_accepted_at"):
        op.drop_column("organisations", "overage_consent_accepted_at")
