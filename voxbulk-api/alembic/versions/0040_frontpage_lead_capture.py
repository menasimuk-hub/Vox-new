"""Front page lead capture: provider, prompt, KB, lead code, recordings.

Revision ID: 0040_frontpage_lead_capture
Revises: 0039_agent_services_kb_context
Create Date: 2026-05-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_frontpage_lead_capture"
down_revision = "0039_agent_services_kb_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "frontpage_call_settings",
        sa.Column("voice_provider", sa.String(length=20), nullable=False, server_default="vapi"),
    )
    op.add_column("frontpage_call_settings", sa.Column("provider_agent_id", sa.String(length=128), nullable=True))
    op.add_column("frontpage_call_settings", sa.Column("prompt_description", sa.Text(), nullable=True))
    op.add_column("frontpage_call_settings", sa.Column("system_prompt", sa.Text(), nullable=True))
    op.add_column("frontpage_call_settings", sa.Column("kb_file_ids", sa.Text(), nullable=True))
    op.add_column("frontpage_call_settings", sa.Column("kb_context", sa.Text(), nullable=True))

    op.add_column("frontpage_lead_calls", sa.Column("lead_code", sa.String(length=32), nullable=True))
    op.create_index("ix_frontpage_lead_calls_lead_code", "frontpage_lead_calls", ["lead_code"], unique=True)
    op.add_column("frontpage_lead_calls", sa.Column("voice_provider", sa.String(length=20), nullable=True))
    op.add_column("frontpage_lead_calls", sa.Column("provider_agent_id", sa.String(length=128), nullable=True))
    op.add_column("frontpage_lead_calls", sa.Column("recording_path", sa.String(length=512), nullable=True))
    op.add_column("frontpage_lead_calls", sa.Column("duration_seconds", sa.Integer(), nullable=True))
    op.add_column("frontpage_lead_calls", sa.Column("lead_data_json", sa.Text(), nullable=True))
    op.add_column("frontpage_lead_calls", sa.Column("recommendation", sa.String(length=30), nullable=True))
    op.add_column("frontpage_lead_calls", sa.Column("sentiment", sa.String(length=30), nullable=True))
    op.add_column("frontpage_lead_calls", sa.Column("completed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("frontpage_lead_calls", "completed_at")
    op.drop_column("frontpage_lead_calls", "sentiment")
    op.drop_column("frontpage_lead_calls", "recommendation")
    op.drop_column("frontpage_lead_calls", "lead_data_json")
    op.drop_column("frontpage_lead_calls", "duration_seconds")
    op.drop_column("frontpage_lead_calls", "recording_path")
    op.drop_column("frontpage_lead_calls", "provider_agent_id")
    op.drop_column("frontpage_lead_calls", "voice_provider")
    op.drop_index("ix_frontpage_lead_calls_lead_code", table_name="frontpage_lead_calls")
    op.drop_column("frontpage_lead_calls", "lead_code")

    op.drop_column("frontpage_call_settings", "kb_context")
    op.drop_column("frontpage_call_settings", "kb_file_ids")
    op.drop_column("frontpage_call_settings", "system_prompt")
    op.drop_column("frontpage_call_settings", "prompt_description")
    op.drop_column("frontpage_call_settings", "provider_agent_id")
    op.drop_column("frontpage_call_settings", "voice_provider")
