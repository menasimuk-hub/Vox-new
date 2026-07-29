"""Unique wallet ledger rows per provider payment reference.

Revision ID: 0208_wallet_tx_provider_ref_unique
Revises: 0207_ai_team_inbound_read_at
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0208_wallet_tx_provider_ref_unique"
down_revision = "0207_ai_team_inbound_read_at"
branch_labels = None
depends_on = None

_UQ = "uq_wallet_tx_provider_reference"


def _has_unique(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for uq in inspector.get_unique_constraints("wallet_transactions"):
        if uq.get("name") == name:
            return True
    # SQLite / some dialects expose uniques via indexes
    for ix in inspector.get_indexes("wallet_transactions"):
        if ix.get("name") == name and ix.get("unique"):
            return True
    return False


def upgrade() -> None:
    if _has_unique(_UQ):
        return
    # Drop duplicate succeeded rows keeping the earliest id per (provider, provider_reference).
    op.execute(
        sa.text(
            """
            DELETE FROM wallet_transactions
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY provider, provider_reference
                               ORDER BY created_at ASC, id ASC
                           ) AS rn
                    FROM wallet_transactions
                    WHERE provider IS NOT NULL
                      AND provider_reference IS NOT NULL
                      AND TRIM(provider_reference) != ''
                ) ranked
                WHERE rn > 1
            )
            """
        )
    )
    op.create_unique_constraint(_UQ, "wallet_transactions", ["provider", "provider_reference"])


def downgrade() -> None:
    if _has_unique(_UQ):
        op.drop_constraint(_UQ, "wallet_transactions", type_="unique")
