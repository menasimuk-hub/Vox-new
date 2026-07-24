"""Expo lead-capture foundation tables.

Revision ID: 0180_expo_foundation
Revises: 0179_feedback_created_by_user
Create Date: 2026-07-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0180_expo_foundation"
down_revision = "0179_feedback_created_by_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expo_industries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("addon_question", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expo_industries_slug", "expo_industries", ["slug"], unique=True)

    op.create_table(
        "expo_packages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("market_zone", sa.String(length=8), nullable=False, server_default="gb"),
        sa.Column("tier", sa.String(length=32), nullable=False, server_default="starter"),
        sa.Column("max_booths", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_assets", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("lead_scoring_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("post_show_followup_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("post_event_survey_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("ai_summary_report_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expo_packages_plan_id", "expo_packages", ["plan_id"], unique=True)
    op.create_index("ix_expo_packages_market_zone", "expo_packages", ["market_zone"])
    op.create_index("ix_expo_packages_tier", "expo_packages", ["tier"])

    op.create_table(
        "expo_exhibitions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("industry_id", sa.String(length=36), sa.ForeignKey("expo_industries.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("venue", sa.String(length=255), nullable=True),
        sa.Column("starts_on", sa.DateTime(), nullable=True),
        sa.Column("ends_on", sa.DateTime(), nullable=True),
        sa.Column("preferred_language", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expo_exhibitions_org_id", "expo_exhibitions", ["org_id"])
    op.create_index("ix_expo_exhibitions_industry_id", "expo_exhibitions", ["industry_id"])

    op.create_table(
        "expo_booths",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("exhibition_id", sa.String(length=36), sa.ForeignKey("expo_exhibitions.id"), nullable=False),
        sa.Column("package_id", sa.String(length=36), sa.ForeignKey("expo_packages.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("company_display_name", sa.String(length=255), nullable=False),
        sa.Column("booth_code", sa.String(length=64), nullable=True),
        sa.Column("qr_token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("scan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("question_config_json", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expo_booths_org_id", "expo_booths", ["org_id"])
    op.create_index("ix_expo_booths_exhibition_id", "expo_booths", ["exhibition_id"])
    op.create_index("ix_expo_booths_qr_token", "expo_booths", ["qr_token"], unique=True)

    op.create_table(
        "expo_booth_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("booth_id", sa.String(length=36), sa.ForeignKey("expo_booths.id"), nullable=False),
        sa.Column("asset_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="pdf"),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("match_keywords", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expo_booth_assets_org_id", "expo_booth_assets", ["org_id"])
    op.create_index("ix_expo_booth_assets_booth_id", "expo_booth_assets", ["booth_id"])

    op.create_table(
        "expo_leads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("booth_id", sa.String(length=36), sa.ForeignKey("expo_booths.id"), nullable=False),
        sa.Column("exhibition_id", sa.String(length=36), sa.ForeignKey("expo_exhibitions.id"), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("visitor_phone", sa.String(length=64), nullable=True),
        sa.Column("visitor_email", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("interest", sa.Text(), nullable=True),
        sa.Column("buying_timeline", sa.String(length=255), nullable=True),
        sa.Column("detected_language", sa.String(length=32), nullable=True),
        sa.Column("country_hint", sa.String(length=64), nullable=True),
        sa.Column("lead_score", sa.String(length=16), nullable=True),
        sa.Column("consent_acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("offer_sent_at", sa.DateTime(), nullable=True),
        sa.Column("assets_sent_json", sa.Text(), nullable=True),
        sa.Column("follow_up_status", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expo_leads_org_id", "expo_leads", ["org_id"])
    op.create_index("ix_expo_leads_booth_id", "expo_leads", ["booth_id"])
    op.create_index("ix_expo_leads_session_id", "expo_leads", ["session_id"])
    op.create_index("ix_expo_leads_lead_score", "expo_leads", ["lead_score"])

    op.create_table(
        "expo_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("booth_id", sa.String(length=36), sa.ForeignKey("expo_booths.id"), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="whatsapp"),
        sa.Column("visitor_phone", sa.String(length=64), nullable=False),
        sa.Column("visitor_email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detected_language", sa.String(length=16), nullable=True),
        sa.Column("session_state_json", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expo_sessions_org_id", "expo_sessions", ["org_id"])
    op.create_index("ix_expo_sessions_booth_id", "expo_sessions", ["booth_id"])
    op.create_index("ix_expo_sessions_visitor_phone", "expo_sessions", ["visitor_phone"])

    op.create_table(
        "expo_responses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("expo_sessions.id"), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("booth_id", sa.String(length=36), sa.ForeignKey("expo_booths.id"), nullable=False),
        sa.Column("question_key", sa.String(length=128), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=True),
        sa.Column("answer_text_en", sa.Text(), nullable=True),
        sa.Column("step_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_source", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_expo_responses_session_id", "expo_responses", ["session_id"])
    op.create_index("ix_expo_responses_org_id", "expo_responses", ["org_id"])

    op.create_table(
        "expo_voice_note_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("expo_sessions.id"), nullable=False),
        sa.Column("booth_id", sa.String(length=36), sa.ForeignKey("expo_booths.id"), nullable=False),
        sa.Column("inbound_message_id", sa.String(length=128), nullable=True),
        sa.Column("provider_media_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("inbound_message_id", "provider_media_id", name="uq_expo_voice_note_inbound_media"),
    )
    op.create_index("ix_expo_voice_note_jobs_org_id", "expo_voice_note_jobs", ["org_id"])
    op.create_index("ix_expo_voice_note_jobs_session_id", "expo_voice_note_jobs", ["session_id"])
    op.create_index("ix_expo_voice_note_jobs_status", "expo_voice_note_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("expo_voice_note_jobs")
    op.drop_table("expo_responses")
    op.drop_table("expo_sessions")
    op.drop_table("expo_leads")
    op.drop_table("expo_booth_assets")
    op.drop_table("expo_booths")
    op.drop_table("expo_exhibitions")
    op.drop_table("expo_packages")
    op.drop_table("expo_industries")
