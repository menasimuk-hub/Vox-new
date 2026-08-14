"""0252 — User preferred (main) organisation for multi-company login.

Revision ID: 0252_user_preferred_org
Revises: 0251_smart_card_billable_seats
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0252_user_preferred_org"
down_revision = "0251_smart_card_billable_seats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("preferred_org_id", sa.String(length=36), nullable=True))
    op.create_index("ix_users_preferred_org_id", "users", ["preferred_org_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_preferred_org_id", table_name="users")
    op.drop_column("users", "preferred_org_id")
