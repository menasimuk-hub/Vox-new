"""smtp settings + email templates

Revision ID: 0020_smtp_email_templates
Revises: 0019_oauth_identities
"""

from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "0020_smtp_email_templates"
down_revision = "0019_oauth_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smtp_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("username", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("from_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("from_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("use_tls", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("use_ssl", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    now = datetime.utcnow()
    op.bulk_insert(
        sa.table(
            "smtp_settings",
            sa.column("id", sa.Integer),
            sa.column("host", sa.String),
            sa.column("port", sa.Integer),
            sa.column("username", sa.String),
            sa.column("password_encrypted", sa.Text),
            sa.column("from_name", sa.String),
            sa.column("from_email", sa.String),
            sa.column("use_tls", sa.Boolean),
            sa.column("use_ssl", sa.Boolean),
            sa.column("is_enabled", sa.Boolean),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {
                "id": 1,
                "host": "",
                "port": 587,
                "username": "",
                "password_encrypted": None,
                "from_name": "",
                "from_email": "",
                "use_tls": True,
                "use_ssl": False,
                "is_enabled": False,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )

    op.create_table(
        "email_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_key", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_email_templates_template_key", "email_templates", ["template_key"], unique=False)
    op.create_unique_constraint("uq_email_templates_key", "email_templates", ["template_key"])

    templates = [
        (
            "new_user",
            "Welcome to VOXBULK",
            "Hello,\n\nYour account has been created. You can sign in with the email and password you chose.\n\n— Rekovo",
        ),
        (
            "forgot_password",
            "Reset your password",
            "Hello,\n\nWe received a request to reset your password. Use the secure link from your app to choose a new password.\n\nIf you did not request this, you can ignore this email.\n\n— Rekovo",
        ),
        (
            "new_invoice",
            "New invoice",
            "Hello,\n\nA new invoice is available in your billing area. Please review the amount and due date.\n\n— Rekovo",
        ),
        (
            "payment_failed",
            "Payment issue",
            "Hello,\n\nWe could not process a recent payment. Please update your payment method or retry the payment to avoid interruption.\n\n— Rekovo",
        ),
        (
            "general_notification",
            "Notification",
            "Hello,\n\nYou have a new notification in VOXBULK. Sign in to your dashboard for details.\n\n— Rekovo",
        ),
    ]

    rows = []
    for key, subj, body in templates:
        rows.append(
            {
                "template_key": key,
                "subject": subj,
                "body": body,
                "is_enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        )
    op.bulk_insert(
        sa.table(
            "email_templates",
            sa.column("template_key", sa.String),
            sa.column("subject", sa.String),
            sa.column("body", sa.Text),
            sa.column("is_enabled", sa.Boolean),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        rows,
    )


def downgrade() -> None:
    op.drop_constraint("uq_email_templates_key", "email_templates", type_="unique")
    op.drop_index("ix_email_templates_template_key", table_name="email_templates")
    op.drop_table("email_templates")
    op.drop_table("smtp_settings")
