"""Rewrite sales WhatsApp templates for Meta/Telnyx button templates.

Revision ID: 0063_sales_wa_button_templates
Revises: 0062_sales_offer_templates
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.data.sales_automation_defaults import (
    SALES_OFFER_FOLLOWUP_WHATSAPP_BODY,
    SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY,
    SALES_OPT_IN_WHATSAPP_BODY,
)
from app.data.sales_offer_email_default import SALES_OFFER_WHATSAPP_BODY

revision = "0063_sales_wa_button_templates"
down_revision = "0062_sales_offer_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "whatsapp_templates" not in set(insp.get_table_names()):
        return

    for key, body in (
        ("sales_opt_in", SALES_OPT_IN_WHATSAPP_BODY),
        ("sales_offer", SALES_OFFER_WHATSAPP_BODY),
        ("sales_offer_followup", SALES_OFFER_FOLLOWUP_WHATSAPP_BODY),
        ("sales_offer_keyword_confirm", SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY),
    ):
        bind.execute(
            sa.text(
                "UPDATE whatsapp_templates SET body = :body, updated_at = CURRENT_TIMESTAMP WHERE template_key = :key"
            ),
            {"key": key, "body": body},
        )


def downgrade() -> None:
    pass
