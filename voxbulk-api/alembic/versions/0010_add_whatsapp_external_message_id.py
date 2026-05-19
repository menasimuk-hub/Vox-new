"""add whatsapp external message id

Revision ID: 0010_add_whatsapp_external_message_id
Revises: 0009_add_dentally_external_ids
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_add_whatsapp_external_message_id"
down_revision = "0009_add_dentally_external_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("whatsapp_logs", sa.Column("external_message_id", sa.String(length=100), nullable=True))
    op.create_index("ix_whatsapp_logs_external_message_id", "whatsapp_logs", ["external_message_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_whatsapp_logs_external_message_id", table_name="whatsapp_logs")
    op.drop_column("whatsapp_logs", "external_message_id")

