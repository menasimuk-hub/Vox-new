"""0257 — Optional TOTP MFA for platform superusers.

Revision ID: 0257_user_mfa_totp
Revises: 0256_billing_audit_hardening
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0257_user_mfa_totp"
down_revision = "0256_billing_audit_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_totp_secret", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_totp_secret")
