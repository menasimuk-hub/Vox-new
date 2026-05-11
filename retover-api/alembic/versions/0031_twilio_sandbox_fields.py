"""twilio sandbox fields

Revision ID: 0031_twilio_sandbox_fields
Revises: 0030_billing_redirect_flows
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0031_twilio_sandbox_fields"
down_revision = "0030_billing_redirect_flows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("whatsapp_logs", sa.Column("direction", sa.String(length=20), nullable=False, server_default="outbound"))
    op.add_column("whatsapp_logs", sa.Column("from_number", sa.String(length=32), nullable=True))
    op.add_column("whatsapp_logs", sa.Column("body", sa.Text(), nullable=True))
    op.add_column("whatsapp_logs", sa.Column("media_json", sa.Text(), nullable=True))
    op.add_column("call_logs", sa.Column("recording_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("call_logs", "recording_url")
    op.drop_column("whatsapp_logs", "media_json")
    op.drop_column("whatsapp_logs", "body")
    op.drop_column("whatsapp_logs", "from_number")
    op.drop_column("whatsapp_logs", "direction")
