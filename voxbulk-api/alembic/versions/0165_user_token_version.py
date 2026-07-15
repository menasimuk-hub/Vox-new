"""0165 — users.token_version for JWT revocation after password reset.

Revision ID: 0165_user_token_version
Revises: 0164_platform_contact_time
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0165_user_token_version"
down_revision = "0164_platform_contact_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
