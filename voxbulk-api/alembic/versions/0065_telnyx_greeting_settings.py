"""Add editable Telnyx greeting on lead and sales settings.

Revision ID: 0065_telnyx_greeting_settings
Revises: 0064_invoice_documents_vat
"""

from alembic import op
import sqlalchemy as sa

revision = "0065_telnyx_greeting_settings"
down_revision = "0064_invoice_documents_vat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("frontpage_call_settings", sa.Column("telnyx_greeting", sa.Text(), nullable=True))
    op.add_column("lead_sales_settings", sa.Column("telnyx_greeting", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_sales_settings", "telnyx_greeting")
    op.drop_column("frontpage_call_settings", "telnyx_greeting")
