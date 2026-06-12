"""Customer Feedback workflow — location config, marketing, promo wallet, template fields."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0119_customer_feedback_workflow"
down_revision = "0118_account_deletion_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedback_locations",
        sa.Column("selected_survey_type_ids_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "feedback_locations",
        sa.Column("open_question_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "feedback_locations",
        sa.Column("marketing_opt_in_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "feedback_locations",
        sa.Column("survey_config_json", sa.Text(), nullable=True),
    )

    op.add_column("feedback_sessions", sa.Column("detected_language", sa.String(length=16), nullable=True))
    op.add_column("feedback_sessions", sa.Column("trigger_dedupe_key", sa.String(length=128), nullable=True))
    op.create_index("ix_feedback_sessions_trigger_dedupe", "feedback_sessions", ["trigger_dedupe_key"])

    op.add_column("feedback_responses", sa.Column("original_text", sa.Text(), nullable=True))
    op.add_column("feedback_responses", sa.Column("answer_text_en", sa.Text(), nullable=True))

    op.add_column("feedback_wa_templates", sa.Column("step_role", sa.String(length=32), nullable=True))
    op.add_column(
        "feedback_wa_templates",
        sa.Column("language", sa.String(length=16), nullable=False, server_default="en_GB"),
    )
    op.add_column("feedback_wa_templates", sa.Column("buttons_json", sa.Text(), nullable=True))
    op.add_column(
        "feedback_wa_templates",
        sa.Column("meta_category", sa.String(length=16), nullable=False, server_default="utility"),
    )
    op.add_column(
        "feedback_wa_templates",
        sa.Column("telnyx_sync_status", sa.String(length=32), nullable=False, server_default="draft"),
    )

    op.add_column(
        "feedback_packages",
        sa.Column("promo_message_cost_minor", sa.Integer(), nullable=False, server_default="5"),
    )

    op.add_column("plans", sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    op.create_table(
        "feedback_marketing_subscribers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("location_id", sa.String(length=36), sa.ForeignKey("feedback_locations.id"), nullable=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("feedback_sessions.id"), nullable=True),
        sa.Column("phone_e164", sa.String(length=32), nullable=False),
        sa.Column("consent_version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("opted_in_at", sa.DateTime(), nullable=False),
        sa.Column("opted_out_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "phone_e164", name="uq_feedback_marketing_org_phone"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_marketing_subscribers_org", "feedback_marketing_subscribers", ["org_id"])

    op.create_table(
        "feedback_promo_wallets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="GBP"),
        sa.Column("balance_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", name="uq_feedback_promo_wallets_org"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "feedback_promo_sends",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("feedback_promo_sends")
    op.drop_table("feedback_promo_wallets")
    op.drop_index("ix_feedback_marketing_subscribers_org", table_name="feedback_marketing_subscribers")
    op.drop_table("feedback_marketing_subscribers")
    op.drop_column("plans", "is_frozen")
    op.drop_column("feedback_packages", "promo_message_cost_minor")
    op.drop_column("feedback_wa_templates", "telnyx_sync_status")
    op.drop_column("feedback_wa_templates", "meta_category")
    op.drop_column("feedback_wa_templates", "buttons_json")
    op.drop_column("feedback_wa_templates", "language")
    op.drop_column("feedback_wa_templates", "step_role")
    op.drop_column("feedback_responses", "answer_text_en")
    op.drop_column("feedback_responses", "original_text")
    op.drop_index("ix_feedback_sessions_trigger_dedupe", table_name="feedback_sessions")
    op.drop_column("feedback_sessions", "trigger_dedupe_key")
    op.drop_column("feedback_sessions", "detected_language")
    op.drop_column("feedback_locations", "survey_config_json")
    op.drop_column("feedback_locations", "marketing_opt_in_enabled")
    op.drop_column("feedback_locations", "open_question_enabled")
    op.drop_column("feedback_locations", "selected_survey_type_ids_json")
