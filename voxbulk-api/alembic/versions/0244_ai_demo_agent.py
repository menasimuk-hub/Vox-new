"""AI Demo Agent tables: requests, sessions, knowledge bases, settings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0244_ai_demo_agent"
down_revision = "0243_custom_package_collation"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if not _has_table("demo_requests"):
        op.create_table(
            "demo_requests",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("source", sa.String(20), nullable=False, server_default="web"),
            sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
            sa.Column("contact_name", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("company_name", sa.String(255), nullable=False),
            sa.Column("whatsapp_e164", sa.String(40), nullable=False),
            sa.Column("website", sa.String(512), nullable=False),
            sa.Column("preferred_language", sa.String(10), nullable=False, server_default="en"),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("admin_notes", sa.Text(), nullable=True),
            sa.Column("approved_by", sa.String(36), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("rejected_at", sa.DateTime(), nullable=True),
            sa.Column("reject_reason", sa.String(500), nullable=True),
            sa.Column("conversation_memory", sa.Text(), nullable=True),
            sa.Column("lead_sales_task_id", sa.String(36), nullable=True),
            sa.Column("frontpage_lead_call_id", sa.String(36), nullable=True),
            sa.Column("demo_completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_demo_requests_source", "demo_requests", ["source"])
        op.create_index("ix_demo_requests_status", "demo_requests", ["status"])
        op.create_index("ix_demo_requests_email", "demo_requests", ["email"])
        op.create_index("ix_demo_requests_created_at", "demo_requests", ["created_at"])
        op.create_index("ix_demo_requests_lead_sales_task_id", "demo_requests", ["lead_sales_task_id"])
        op.create_index("ix_demo_requests_frontpage_lead_call_id", "demo_requests", ["frontpage_lead_call_id"])

    if not _has_table("demo_sessions"):
        op.create_table(
            "demo_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("request_id", sa.String(36), nullable=False),
            sa.Column("token_hmac", sa.String(64), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="issued"),
            sa.Column("voice", sa.String(80), nullable=True),
            sa.Column("language", sa.String(10), nullable=False, server_default="en"),
            sa.Column("active_service_code", sa.String(40), nullable=True),
            sa.Column("services_explored", sa.Text(), nullable=True),
            sa.Column("questions_asked", sa.Text(), nullable=True),
            sa.Column("volume_needs", sa.Text(), nullable=True),
            sa.Column("ui_events_log", sa.Text(), nullable=True),
            sa.Column("transcript_log", sa.Text(), nullable=True),
            sa.Column("provider_call_id", sa.String(128), nullable=True),
            sa.Column("frontpage_lead_call_id", sa.String(36), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_demo_sessions_request_id", "demo_sessions", ["request_id"])
        op.create_index("ix_demo_sessions_token_hmac", "demo_sessions", ["token_hmac"], unique=True)
        op.create_index("ix_demo_sessions_status", "demo_sessions", ["status"])
        op.create_index("ix_demo_sessions_expires_at", "demo_sessions", ["expires_at"])
        op.create_index("ix_demo_sessions_provider_call_id", "demo_sessions", ["provider_call_id"])
        op.create_index("ix_demo_sessions_frontpage_lead_call_id", "demo_sessions", ["frontpage_lead_call_id"])

    if not _has_table("demo_knowledge_bases"):
        op.create_table(
            "demo_knowledge_bases",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("service_code", sa.String(40), nullable=False),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("system_prompt", sa.Text(), nullable=False),
            sa.Column("fact_sheet", sa.Text(), nullable=False),
            sa.Column("demo_script", sa.Text(), nullable=False),
            sa.Column("tool_subset", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_demo_knowledge_bases_service_code", "demo_knowledge_bases", ["service_code"], unique=True)

    if not _has_table("demo_platform_settings"):
        op.create_table(
            "demo_platform_settings",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("provider_agent_id", sa.String(128), nullable=True),
            sa.Column("default_voice", sa.String(80), nullable=True),
            sa.Column("soft_cap_minutes", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("from_email", sa.String(255), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    for table in (
        "demo_platform_settings",
        "demo_knowledge_bases",
        "demo_sessions",
        "demo_requests",
    ):
        if _has_table(table):
            op.drop_table(table)
