"""frontpage call settings and transcripts

Revision ID: 0037_frontpage_call_settings
Revises: 0036_frontpage_lead_calls
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0037_frontpage_call_settings"
down_revision = "0036_frontpage_lead_calls"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "frontpage_call_settings" not in tables:
        op.create_table(
            "frontpage_call_settings",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("agent_id", sa.String(length=36), nullable=True),
            sa.Column("agent_slug", sa.String(length=120), nullable=True),
            sa.Column("stt_provider", sa.String(length=40), nullable=False, server_default="deepgram"),
            sa.Column("llm_provider", sa.String(length=40), nullable=False, server_default="groq"),
            sa.Column("tts_provider", sa.String(length=40), nullable=False, server_default="cartesia"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_frontpage_call_settings_agent_id", "frontpage_call_settings", ["agent_id"])

    if "frontpage_lead_calls" in tables:
        if not _has_column(inspector, "frontpage_lead_calls", "agent_id"):
            op.add_column("frontpage_lead_calls", sa.Column("agent_id", sa.String(length=36), nullable=True))
            op.create_index("ix_frontpage_lead_calls_agent_id", "frontpage_lead_calls", ["agent_id"])
        if not _has_column(inspector, "frontpage_lead_calls", "agent_slug"):
            op.add_column("frontpage_lead_calls", sa.Column("agent_slug", sa.String(length=120), nullable=True))
        if not _has_column(inspector, "frontpage_lead_calls", "transcript_text"):
            op.add_column("frontpage_lead_calls", sa.Column("transcript_text", sa.Text(), nullable=True))
        if not _has_column(inspector, "frontpage_lead_calls", "agent_response_text"):
            op.add_column("frontpage_lead_calls", sa.Column("agent_response_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("frontpage_lead_calls", "agent_response_text")
    op.drop_column("frontpage_lead_calls", "transcript_text")
    op.drop_column("frontpage_lead_calls", "agent_slug")
    op.drop_index("ix_frontpage_lead_calls_agent_id", table_name="frontpage_lead_calls")
    op.drop_column("frontpage_lead_calls", "agent_id")
    op.drop_index("ix_frontpage_call_settings_agent_id", table_name="frontpage_call_settings")
    op.drop_table("frontpage_call_settings")
