"""Usage metering + messaging template seeds.

Revision ID: 0056_usage_metering_templates
Revises: 0055_onboarding_auto_approve_setting
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056_usage_metering_templates"
down_revision = "0055_onboarding_auto_approve_setting"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("call_logs", "usage_metered"):
        op.add_column("call_logs", sa.Column("usage_metered", sa.Boolean(), nullable=False, server_default=sa.false()))

    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "whatsapp_templates" in insp.get_table_names():
        exists = bind.execute(
            sa.text("SELECT 1 FROM whatsapp_templates WHERE template_key = 'sales_offer' LIMIT 1")
        ).scalar()
        if not exists:
            from app.data.sales_offer_email_default import SALES_OFFER_WHATSAPP_BODY

            bind.execute(
                sa.text(
                    "INSERT INTO whatsapp_templates (template_key, name, body, is_enabled, created_at, updated_at) "
                    "VALUES ('sales_offer', 'Sales offer link', :body, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"body": SALES_OFFER_WHATSAPP_BODY},
            )


def downgrade() -> None:
    if _has_column("call_logs", "usage_metered"):
        op.drop_column("call_logs", "usage_metered")
    op.execute(sa.text("DELETE FROM whatsapp_templates WHERE template_key = 'sales_offer'"))
