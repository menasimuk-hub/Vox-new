"""frontpage lead calls

Revision ID: 0036_frontpage_lead_calls
Revises: 0035_onboarding_service_api_configs
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0036_frontpage_lead_calls"
down_revision = "0035_onboarding_service_api_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "frontpage_lead_calls" in set(inspector.get_table_names()):
        return

    op.create_table(
        "frontpage_lead_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="frontpage_talk_to_us"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="created"),
        sa.Column("provider_call_id", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_frontpage_lead_calls_email", "frontpage_lead_calls", ["email"])
    op.create_index("ix_frontpage_lead_calls_source", "frontpage_lead_calls", ["source"])
    op.create_index("ix_frontpage_lead_calls_status", "frontpage_lead_calls", ["status"])
    op.create_index("ix_frontpage_lead_calls_provider_call_id", "frontpage_lead_calls", ["provider_call_id"])


def downgrade() -> None:
    op.drop_index("ix_frontpage_lead_calls_provider_call_id", table_name="frontpage_lead_calls")
    op.drop_index("ix_frontpage_lead_calls_status", table_name="frontpage_lead_calls")
    op.drop_index("ix_frontpage_lead_calls_source", table_name="frontpage_lead_calls")
    op.drop_index("ix_frontpage_lead_calls_email", table_name="frontpage_lead_calls")
    op.drop_table("frontpage_lead_calls")
