"""Add sales_offer system email template

Revision ID: 0053_sales_offer_email_template
Revises: 0052_pricing_promo_usage
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

from app.data.sales_offer_email_default import SALES_OFFER_EMAIL_BODY, SALES_OFFER_EMAIL_SUBJECT

revision = "0053_sales_offer_email_template"
down_revision = "0052_pricing_promo_usage"
branch_labels = None
depends_on = None

NOW = datetime.utcnow()


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM email_templates WHERE template_key = :key LIMIT 1"),
        {"key": "sales_offer"},
    ).scalar()
    if exists:
        bind.execute(
            sa.text(
                """
                UPDATE email_templates
                SET title = :title, subject = :subject, body = :body, is_enabled = true, updated_at = :updated_at
                WHERE template_key = :key
                """
            ),
            {
                "key": "sales_offer",
                "title": "Sales offer link",
                "subject": SALES_OFFER_EMAIL_SUBJECT,
                "body": SALES_OFFER_EMAIL_BODY,
                "updated_at": NOW,
            },
        )
        return

    op.bulk_insert(
        sa.table(
            "email_templates",
            sa.column("template_key", sa.String),
            sa.column("title", sa.String),
            sa.column("subject", sa.String),
            sa.column("body", sa.Text),
            sa.column("is_enabled", sa.Boolean),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {
                "template_key": "sales_offer",
                "title": "Sales offer link",
                "subject": SALES_OFFER_EMAIL_SUBJECT,
                "body": SALES_OFFER_EMAIL_BODY,
                "is_enabled": True,
                "created_at": NOW,
                "updated_at": NOW,
            }
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM email_templates WHERE template_key = 'sales_offer'"))
