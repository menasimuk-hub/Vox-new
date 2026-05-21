"""Refresh sales offer WhatsApp/email templates for survey + interview promos.

Revision ID: 0060_sales_offer_template_refresh
Revises: 0059_promo_service_credits
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.data.sales_automation_defaults import (
    SALES_OFFER_FOLLOWUP_WHATSAPP_BODY,
    SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY,
)
from app.data.sales_offer_email_default import SALES_OFFER_EMAIL_BODY, SALES_OFFER_WHATSAPP_BODY

revision = "0060_sales_offer_template_refresh"
down_revision = "0059_promo_service_credits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "whatsapp_templates" in tables:
        for key, body in (
            ("sales_offer", SALES_OFFER_WHATSAPP_BODY),
            ("sales_offer_followup", SALES_OFFER_FOLLOWUP_WHATSAPP_BODY),
            ("sales_offer_keyword_confirm", SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY),
        ):
            bind.execute(
                sa.text("UPDATE whatsapp_templates SET body = :body, updated_at = CURRENT_TIMESTAMP WHERE template_key = :key"),
                {"key": key, "body": body},
            )

    if "email_templates" in tables:
        bind.execute(
            sa.text(
                "UPDATE email_templates SET body = :body, updated_at = CURRENT_TIMESTAMP WHERE template_key = 'sales_offer'"
            ),
            {"body": SALES_OFFER_EMAIL_BODY},
        )


def downgrade() -> None:
    pass
