"""Unique promo redemption per (promo_offer_id, org_id).

Revision ID: 0208_promo_redemption_org_unique
Revises: 0207_ai_team_inbound_read_at
Create Date: 2026-07-29

Note: other open remediation PRs also claim 0208_* off 0207; rebase/merge heads when landing the stack.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0208_promo_redemption_org_unique"
down_revision = "0207_ai_team_inbound_read_at"
branch_labels = None
depends_on = None

_UQ = "uq_promo_redemption_offer_org"


def _has_unique(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for uq in inspector.get_unique_constraints("promo_redemptions"):
        if uq.get("name") == name:
            return True
    for ix in inspector.get_indexes("promo_redemptions"):
        if ix.get("name") == name and ix.get("unique"):
            return True
    return False


def upgrade() -> None:
    if _has_unique(_UQ):
        return
    # Keep earliest redemption per (promo, org); drop later duplicates before unique.
    op.execute(
        sa.text(
            """
            DELETE FROM promo_redemptions
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY promo_offer_id, org_id
                               ORDER BY redeemed_at ASC, id ASC
                           ) AS rn
                    FROM promo_redemptions
                ) ranked
                WHERE rn > 1
            )
            """
        )
    )
    op.create_unique_constraint(_UQ, "promo_redemptions", ["promo_offer_id", "org_id"])


def downgrade() -> None:
    if _has_unique(_UQ):
        op.drop_constraint(_UQ, "promo_redemptions", type_="unique")
