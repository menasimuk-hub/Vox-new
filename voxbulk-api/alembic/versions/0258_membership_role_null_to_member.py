"""0258 — Backfill empty membership roles; never treat NULL as owner.

Revision ID: 0258_membership_role_null_to_member
Revises: 0257_user_mfa_totp
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0258_membership_role_null_to_member"
down_revision = "0257_user_mfa_totp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Promote one legacy NULL/empty row to owner per org that has no owner, then set rest to member."""
    conn = op.get_bind()

    # Orgs that already have at least one explicit owner — leave those owners alone.
    # Orgs with no owner: pick the oldest NULL/empty membership as owner (legacy creator).
    org_ids = conn.execute(sa.text("SELECT DISTINCT org_id FROM organisation_memberships")).fetchall()
    for (org_id,) in org_ids:
        has_owner = conn.execute(
            sa.text(
                "SELECT 1 FROM organisation_memberships "
                "WHERE org_id = :org_id AND LOWER(TRIM(COALESCE(role, ''))) = 'owner' "
                "LIMIT 1"
            ),
            {"org_id": org_id},
        ).fetchone()
        if has_owner:
            continue
        oldest = conn.execute(
            sa.text(
                "SELECT id FROM organisation_memberships "
                "WHERE org_id = :org_id "
                "AND (role IS NULL OR TRIM(role) = '') "
                "ORDER BY created_at ASC, id ASC "
                "LIMIT 1"
            ),
            {"org_id": org_id},
        ).fetchone()
        if oldest is None:
            # No NULL rows — try any membership as last resort
            oldest = conn.execute(
                sa.text(
                    "SELECT id FROM organisation_memberships "
                    "WHERE org_id = :org_id "
                    "ORDER BY created_at ASC, id ASC "
                    "LIMIT 1"
                ),
                {"org_id": org_id},
            ).fetchone()
        if oldest is not None:
            conn.execute(
                sa.text("UPDATE organisation_memberships SET role = 'owner' WHERE id = :id"),
                {"id": oldest[0]},
            )

    conn.execute(
        sa.text(
            "UPDATE organisation_memberships "
            "SET role = 'member' "
            "WHERE role IS NULL OR TRIM(role) = ''"
        )
    )


def downgrade() -> None:
    # Data migration is not safely reversible (cannot restore which rows were NULL).
    pass
