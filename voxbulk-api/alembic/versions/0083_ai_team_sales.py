"""AI Team sales agent — prospects, messages, settings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0083_ai_team_sales"
down_revision = "0082_org_usage_cv_scans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_team_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("search_sector", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("search_country", sa.String(length=64), nullable=False, server_default="United Kingdom"),
        sa.Column("search_company_size", sa.String(length=64), nullable=False, server_default="10-50"),
        # MySQL forbids DEFAULT on TEXT columns — app fills via AiTeamService.get_settings()
        sa.Column("search_title_keywords", sa.Text(), nullable=False),
        sa.Column("search_city_region", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("search_max_per_run", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("search_min_score", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("followup_after_days", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("max_followups", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("sender_name", sa.String(length=128), nullable=False, server_default="VoxBulk team"),
        sa.Column("reply_to_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("from_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("writing_instruction", sa.Text(), nullable=False),
        sa.Column("email_signature", sa.Text(), nullable=False),
        sa.Column("email_language", sa.String(length=32), nullable=False, server_default="en-GB"),
        sa.Column("email_max_words", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("email_tone", sa.String(length=64), nullable=False, server_default="direct"),
        sa.Column("promo_code_prefix", sa.String(length=32), nullable=False, server_default="TRIAL"),
        sa.Column("promo_offer_type", sa.String(length=32), nullable=False, server_default="survey_credits"),
        sa.Column("promo_value", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("promo_expiry_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("promo_max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("promo_code_mode", sa.String(length=32), nullable=False, server_default="unique"),
        sa.Column("smtp_host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("smtp_username", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("smtp_password_enc", sa.Text(), nullable=True),
        sa.Column("inbox_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("resend_sending_domain", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("run_schedule", sa.String(length=64), nullable=False, server_default="daily_08"),
        sa.Column("max_emails_per_day", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("sending_window", sa.String(length=64), nullable=False, server_default="weekday_08_18"),
        sa.Column("auto_fetch_prospects", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("auto_draft_emails", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("auto_followup", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("track_opens", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("notify_on_reply", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("notify_on_promo_used", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("auto_send_without_approval", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("apollo_credit_alert_at", sa.Integer(), nullable=False, server_default="800"),
        sa.Column("agent_paused", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_agent_run_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "ai_team_prospects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("apollo_id", sa.String(length=128), nullable=True),
        sa.Column("first_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("job_title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("company_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("sector", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("country_code", sa.String(length=8), nullable=False, server_default="GB"),
        sa.Column("match_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="apollo"),
        sa.Column("promo_offer_id", sa.String(length=36), sa.ForeignKey("promo_offers.id"), nullable=True),
        sa.Column("draft_subject", sa.String(length=500), nullable=True),
        sa.Column("draft_body", sa.Text(), nullable=True),
        sa.Column("draft_body_html", sa.Text(), nullable=True),
        sa.Column("drafted_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("replied_at", sa.DateTime(), nullable=True),
        sa.Column("converted_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("resend_email_id", sa.String(length=128), nullable=True),
        sa.Column("emails_sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("followups_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("profile_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_ai_team_prospects_email", "ai_team_prospects", ["email"])
    op.create_index("ix_ai_team_prospects_status", "ai_team_prospects", ["status"])
    op.create_index("ix_ai_team_prospects_apollo_id", "ai_team_prospects", ["apollo_id"])
    op.create_index("ix_ai_team_prospects_promo_offer_id", "ai_team_prospects", ["promo_offer_id"])

    op.create_table(
        "ai_team_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("prospect_id", sa.String(length=36), sa.ForeignKey("ai_team_prospects.id"), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="outbound"),
        sa.Column("from_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("to_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("subject", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("resend_email_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_team_messages_prospect_id", "ai_team_messages", ["prospect_id"])

    bind = op.get_bind()
    insp = sa.inspect(bind)
    promo_cols = {c["name"] for c in insp.get_columns("promo_offers")}
    if "ai_team_prospect_id" not in promo_cols:
        op.add_column("promo_offers", sa.Column("ai_team_prospect_id", sa.String(length=36), nullable=True))
        op.create_index("ix_promo_offers_ai_team_prospect_id", "promo_offers", ["ai_team_prospect_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    promo_cols = {c["name"] for c in insp.get_columns("promo_offers")}
    if "ai_team_prospect_id" in promo_cols:
        op.drop_index("ix_promo_offers_ai_team_prospect_id", table_name="promo_offers")
        op.drop_column("promo_offers", "ai_team_prospect_id")

    op.drop_index("ix_ai_team_messages_prospect_id", table_name="ai_team_messages")
    op.drop_table("ai_team_messages")
    op.drop_index("ix_ai_team_prospects_promo_offer_id", table_name="ai_team_prospects")
    op.drop_index("ix_ai_team_prospects_apollo_id", table_name="ai_team_prospects")
    op.drop_index("ix_ai_team_prospects_status", table_name="ai_team_prospects")
    op.drop_index("ix_ai_team_prospects_email", table_name="ai_team_prospects")
    op.drop_table("ai_team_prospects")
    op.drop_table("ai_team_settings")
