"""0219 — Emails hub: SMTP username + encrypted password on platform_sender_emails.

Revision ID: 0219_platform_sender_passwords
Revises: 0218_sales_hub_functional
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0219_platform_sender_passwords"
down_revision = "0218_sales_hub_functional"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _column_names("platform_sender_emails")
    if not cols:
        return
    if "smtp_username" not in cols:
        op.add_column(
            "platform_sender_emails",
            sa.Column("smtp_username", sa.String(length=320), nullable=True),
        )
    if "password_encrypted" not in cols:
        op.add_column(
            "platform_sender_emails",
            sa.Column("password_encrypted", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    cols = _column_names("platform_sender_emails")
    if "password_encrypted" in cols:
        op.drop_column("platform_sender_emails", "password_encrypted")
    if "smtp_username" in cols:
        op.drop_column("platform_sender_emails", "smtp_username")
