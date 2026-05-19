"""Lead sales tasks and settings for scheduled Telnyx outbound follow-up.

Revision ID: 0041_lead_sales
Revises: 0040_frontpage_lead_capture
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_lead_sales"
down_revision = "0040_frontpage_lead_capture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_sales_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("telnyx_assistant_id", sa.String(length=128), nullable=True),
        sa.Column("prompt_description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.execute(
        sa.text(
            "INSERT INTO lead_sales_settings (id, telnyx_assistant_id, prompt_description, updated_at) "
            "VALUES ('default', NULL, NULL, CURRENT_TIMESTAMP)"
        )
    )

    op.create_table(
        "lead_sales_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("frontpage_lead_calls.id"), nullable=False, index=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("interest_summary", sa.Text(), nullable=True),
        sa.Column("sales_intent", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("callback_timezone", sa.String(length=80), nullable=True),
        sa.Column("callback_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("telnyx_assistant_id", sa.String(length=128), nullable=True),
        sa.Column("sales_prompt", sa.Text(), nullable=True),
        sa.Column("sales_prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider_call_id", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.Column("call_started_at", sa.DateTime(), nullable=True),
        sa.Column("call_completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lead_sales_tasks")
    op.drop_table("lead_sales_settings")
