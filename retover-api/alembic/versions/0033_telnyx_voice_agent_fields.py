"""telnyx voice agent fields

Revision ID: 0033_telnyx_voice_agent_fields
Revises: 0032_user_twilio_caller_id_verification
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0033_telnyx_voice_agent_fields"
down_revision = "0032_user_twilio_caller_id_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    call_cols = {c["name"] for c in inspector.get_columns("call_logs")}
    indexes = {i["name"] for i in inspector.get_indexes("users")} | {i["name"] for i in inspector.get_indexes("call_logs")}

    def add_user_col(name: str, column: sa.Column) -> None:
        if name not in user_cols:
            op.add_column("users", column)

    def add_call_col(name: str, column: sa.Column) -> None:
        if name not in call_cols:
            op.add_column("call_logs", column)

    add_user_col("telnyx_verified_number_id", sa.Column("telnyx_verified_number_id", sa.String(length=100), nullable=True))
    add_user_col("telnyx_verification_id", sa.Column("telnyx_verification_id", sa.String(length=100), nullable=True))
    add_user_col(
        "telnyx_phone_verification_status",
        sa.Column("telnyx_phone_verification_status", sa.String(length=30), nullable=False, server_default="unverified"),
    )
    add_user_col("telnyx_phone_verification_requested_at", sa.Column("telnyx_phone_verification_requested_at", sa.DateTime(), nullable=True))
    add_user_col("telnyx_phone_verification_completed_at", sa.Column("telnyx_phone_verification_completed_at", sa.DateTime(), nullable=True))
    add_user_col("telnyx_phone_verification_last_error", sa.Column("telnyx_phone_verification_last_error", sa.String(length=500), nullable=True))
    if "ix_users_telnyx_verified_number_id" not in indexes:
        op.create_index("ix_users_telnyx_verified_number_id", "users", ["telnyx_verified_number_id"])
    if "ix_users_telnyx_verification_id" not in indexes:
        op.create_index("ix_users_telnyx_verification_id", "users", ["telnyx_verification_id"])

    add_call_col("user_id", sa.Column("user_id", sa.String(length=36), nullable=True))
    add_call_col("media_stream_id", sa.Column("media_stream_id", sa.String(length=100), nullable=True))
    add_call_col("llm_prompt", sa.Column("llm_prompt", sa.Text(), nullable=True))
    add_call_col("llm_response", sa.Column("llm_response", sa.Text(), nullable=True))
    add_call_col("transcript_text", sa.Column("transcript_text", sa.Text(), nullable=True))
    add_call_col("started_at", sa.Column("started_at", sa.DateTime(), nullable=True))
    add_call_col("answered_at", sa.Column("answered_at", sa.DateTime(), nullable=True))
    add_call_col("ended_at", sa.Column("ended_at", sa.DateTime(), nullable=True))
    add_call_col("last_status_at", sa.Column("last_status_at", sa.DateTime(), nullable=True))
    if "ix_call_logs_user_id" not in indexes:
        op.create_index("ix_call_logs_user_id", "call_logs", ["user_id"])
    if "ix_call_logs_media_stream_id" not in indexes:
        op.create_index("ix_call_logs_media_stream_id", "call_logs", ["media_stream_id"])


def downgrade() -> None:
    op.drop_index("ix_call_logs_media_stream_id", table_name="call_logs")
    op.drop_index("ix_call_logs_user_id", table_name="call_logs")
    for column_name in [
        "last_status_at",
        "ended_at",
        "answered_at",
        "started_at",
        "transcript_text",
        "llm_response",
        "llm_prompt",
        "media_stream_id",
        "user_id",
    ]:
        op.drop_column("call_logs", column_name)
    op.drop_index("ix_users_telnyx_verification_id", table_name="users")
    op.drop_index("ix_users_telnyx_verified_number_id", table_name="users")
    for column_name in [
        "telnyx_phone_verification_last_error",
        "telnyx_phone_verification_completed_at",
        "telnyx_phone_verification_requested_at",
        "telnyx_phone_verification_status",
        "telnyx_verification_id",
        "telnyx_verified_number_id",
    ]:
        op.drop_column("users", column_name)
