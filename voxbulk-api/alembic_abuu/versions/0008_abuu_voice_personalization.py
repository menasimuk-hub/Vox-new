"""Abuu Phase 8: inbound messages with voice transcript support."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_abuu_voice_personalization"
down_revision = "0007_abuu_gaza_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "abuu_inbound_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_phone", sa.String(length=32), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=True),
        sa.Column("source_message_id", sa.String(length=128), nullable=True),
        sa.Column("message_type", sa.String(length=16), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("transcript_confidence", sa.Float(), nullable=True),
        sa.Column("voice_media_url", sa.String(length=1024), nullable=True),
        sa.Column("voice_content_type", sa.String(length=128), nullable=True),
        sa.Column("voice_storage_path", sa.String(length=1024), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["abuu_customers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abuu_inbound_messages_customer_phone", "abuu_inbound_messages", ["customer_phone"])
    op.create_index("ix_abuu_inbound_messages_source_message_id", "abuu_inbound_messages", ["source_message_id"])


def downgrade() -> None:
    op.drop_index("ix_abuu_inbound_messages_source_message_id", table_name="abuu_inbound_messages")
    op.drop_index("ix_abuu_inbound_messages_customer_phone", table_name="abuu_inbound_messages")
    op.drop_table("abuu_inbound_messages")
