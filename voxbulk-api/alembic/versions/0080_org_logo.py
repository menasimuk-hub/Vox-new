"""Add organisation logo storage key.

Revision ID: 0080_org_logo
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0080_org_logo"
down_revision = "0079_org_opt_out_audit_team"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organisations", sa.Column("logo_storage_key", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("organisations", "logo_storage_key")
