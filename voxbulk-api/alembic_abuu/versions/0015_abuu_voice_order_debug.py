"""Voice order pipeline debug logging table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_abuu_voice_order_debug"
down_revision = "0014_abuu_menu_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "abuu_voice_order_debug",
        sa.Column("order_request_id", sa.String(length=36), nullable=False),
        sa.Column("customer_phone", sa.String(length=32), nullable=False),
        sa.Column("message_id", sa.String(length=128), nullable=True),
        sa.Column("pipeline", sa.String(length=32), nullable=False, server_default="agent"),
        sa.Column("audio_media_url", sa.String(length=1024), nullable=True),
        sa.Column("audio_storage_path", sa.String(length=1024), nullable=True),
        sa.Column("audio_content_type", sa.String(length=128), nullable=True),
        sa.Column("audio_file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column("stt_raw_transcript", sa.Text(), nullable=True),
        sa.Column("llm_system_prompt", sa.Text(), nullable=True),
        sa.Column("llm_messages_json", sa.Text(), nullable=True),
        sa.Column("llm_raw_response", sa.Text(), nullable=True),
        sa.Column("parsed_action_json", sa.Text(), nullable=True),
        sa.Column("parse_status", sa.String(length=32), nullable=True),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("parse_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("final_order_json", sa.Text(), nullable=True),
        sa.Column("session_snapshot_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("order_request_id"),
    )
    op.create_index("ix_abuu_voice_order_debug_customer_phone", "abuu_voice_order_debug", ["customer_phone"])
    op.create_index("ix_abuu_voice_order_debug_message_id", "abuu_voice_order_debug", ["message_id"])
    op.create_index("ix_abuu_voice_order_debug_order_id", "abuu_voice_order_debug", ["order_id"])
    op.create_index("ix_abuu_voice_order_debug_created_at", "abuu_voice_order_debug", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_abuu_voice_order_debug_created_at", table_name="abuu_voice_order_debug")
    op.drop_index("ix_abuu_voice_order_debug_order_id", table_name="abuu_voice_order_debug")
    op.drop_index("ix_abuu_voice_order_debug_message_id", table_name="abuu_voice_order_debug")
    op.drop_index("ix_abuu_voice_order_debug_customer_phone", table_name="abuu_voice_order_debug")
    op.drop_table("abuu_voice_order_debug")
