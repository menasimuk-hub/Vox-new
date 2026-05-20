"""whatsapp/sms templates + email template title

Revision ID: 0046_messaging_templates
Revises: 0045_platform_services_orders
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0046_messaging_templates"
down_revision = "0045_platform_services_orders"
branch_labels = None
depends_on = None

NOW = datetime.utcnow()


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("email_templates")} if "email_templates" in insp.get_table_names() else set()
    if "title" not in cols:
        op.add_column("email_templates", sa.Column("title", sa.String(length=200), nullable=False, server_default=""))

    if "whatsapp_templates" not in insp.get_table_names():
        op.create_table(
            "whatsapp_templates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("template_key", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("template_key", name="uq_whatsapp_templates_key"),
        )
        op.create_index("ix_whatsapp_templates_template_key", "whatsapp_templates", ["template_key"])

        op.bulk_insert(
            sa.table(
                "whatsapp_templates",
                sa.column("template_key", sa.String),
                sa.column("name", sa.String),
                sa.column("body", sa.Text),
                sa.column("is_enabled", sa.Boolean),
                sa.column("created_at", sa.DateTime),
                sa.column("updated_at", sa.DateTime),
            ),
            [
                {
                    "template_key": "hello_offer",
                    "name": "Hello offer",
                    "body": "Hey {{first_name}}! Get 20% off your next visit at {{clinic_name}}.",
                    "is_enabled": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                },
                {
                    "template_key": "order_update",
                    "name": "Order update",
                    "body": "Your order #{{order_id}} has been shipped.",
                    "is_enabled": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            ],
        )

    if "sms_templates" not in insp.get_table_names():
        op.create_table(
            "sms_templates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("template_key", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("template_key", name="uq_sms_templates_key"),
        )
        op.create_index("ix_sms_templates_template_key", "sms_templates", ["template_key"])

        op.bulk_insert(
            sa.table(
                "sms_templates",
                sa.column("template_key", sa.String),
                sa.column("name", sa.String),
                sa.column("body", sa.Text),
                sa.column("is_enabled", sa.Boolean),
                sa.column("created_at", sa.DateTime),
                sa.column("updated_at", sa.DateTime),
            ),
            [
                {
                    "template_key": "verification",
                    "name": "Verification",
                    "body": "Your code is {{code}}. Valid for 10 minutes.",
                    "is_enabled": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                },
                {
                    "template_key": "appointment_reminder",
                    "name": "Appointment reminder",
                    "body": "Reminder: appointment on {{date}} at {{time}} with {{clinic_name}}.",
                    "is_enabled": True,
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            ],
        )


def downgrade() -> None:
    op.drop_index("ix_sms_templates_template_key", table_name="sms_templates")
    op.drop_table("sms_templates")
    op.drop_index("ix_whatsapp_templates_template_key", table_name="whatsapp_templates")
    op.drop_table("whatsapp_templates")
    op.drop_column("email_templates", "title")
