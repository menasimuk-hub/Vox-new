"""Customer Feedback service foundation + parallel subscription billing."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0115_customer_feedback_foundation"
down_revision = "0114_billing_request_tickets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("service_code", sa.String(32), nullable=False, server_default="voxbulk"),
    )
    op.create_index("ix_subscriptions_org_service", "subscriptions", ["org_id", "service_code"])

    op.add_column(
        "billing_invoices",
        sa.Column("service_code", sa.String(32), nullable=True),
    )
    op.create_index("ix_billing_invoices_service_code", "billing_invoices", ["service_code"])

    op.create_table(
        "feedback_industries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedback_industries_slug", "feedback_industries", ["slug"], unique=True)

    op.create_table(
        "feedback_survey_types",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("industry_id", sa.String(36), sa.ForeignKey("feedback_industries.id"), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("industry_id", "slug", name="uq_feedback_survey_types_industry_slug"),
    )
    op.create_index("ix_feedback_survey_types_industry", "feedback_survey_types", ["industry_id"])

    op.create_table(
        "feedback_packages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("market_zone", sa.String(8), nullable=False, server_default="gb"),
        sa.Column("max_locations", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("wa_units_included", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedback_packages_plan", "feedback_packages", ["plan_id"], unique=True)
    op.create_index("ix_feedback_packages_zone", "feedback_packages", ["market_zone"])

    op.create_table(
        "feedback_usage_periods",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("subscription_id", sa.String(36), sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=True),
        sa.Column("wa_units_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wa_units_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedback_usage_org", "feedback_usage_periods", ["org_id"])

    op.create_table(
        "feedback_wa_senders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("country_code", sa.String(8), nullable=False),
        sa.Column("phone_e164", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedback_wa_senders_country", "feedback_wa_senders", ["country_code"], unique=True)

    op.create_table(
        "feedback_locations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("industry_id", sa.String(36), sa.ForeignKey("feedback_industries.id"), nullable=False),
        sa.Column("survey_type_id", sa.String(36), sa.ForeignKey("feedback_survey_types.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("branch_code", sa.String(64), nullable=True),
        sa.Column("qr_token", sa.String(64), nullable=False),
        sa.Column("wa_sender_country", sa.String(8), nullable=False, server_default="gb"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("scan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedback_locations_org", "feedback_locations", ["org_id"])
    op.create_index("ix_feedback_locations_token", "feedback_locations", ["qr_token"], unique=True)

    op.create_table(
        "feedback_wa_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("industry_id", sa.String(36), sa.ForeignKey("feedback_industries.id"), nullable=True),
        sa.Column("survey_type_id", sa.String(36), sa.ForeignKey("feedback_survey_types.id"), nullable=True),
        sa.Column("step_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("template_key", sa.String(128), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "feedback_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("location_id", sa.String(36), sa.ForeignKey("feedback_locations.id"), nullable=False),
        sa.Column("visitor_phone", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("units_charged", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedback_sessions_org", "feedback_sessions", ["org_id"])
    op.create_index("ix_feedback_sessions_location", "feedback_sessions", ["location_id"])
    op.create_index("ix_feedback_sessions_phone", "feedback_sessions", ["visitor_phone"])

    op.create_table(
        "feedback_responses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("feedback_sessions.id"), nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("location_id", sa.String(36), sa.ForeignKey("feedback_locations.id"), nullable=False),
        sa.Column("survey_type_id", sa.String(36), sa.ForeignKey("feedback_survey_types.id"), nullable=False),
        sa.Column("question_key", sa.String(128), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("step_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedback_responses_org", "feedback_responses", ["org_id"])
    op.create_index("ix_feedback_responses_location", "feedback_responses", ["location_id"])


def downgrade() -> None:
    op.drop_table("feedback_responses")
    op.drop_table("feedback_sessions")
    op.drop_table("feedback_wa_templates")
    op.drop_table("feedback_locations")
    op.drop_table("feedback_wa_senders")
    op.drop_table("feedback_usage_periods")
    op.drop_table("feedback_packages")
    op.drop_table("feedback_survey_types")
    op.drop_table("feedback_industries")
    op.drop_index("ix_billing_invoices_service_code", table_name="billing_invoices")
    op.drop_column("billing_invoices", "service_code")
    op.drop_index("ix_subscriptions_org_service", table_name="subscriptions")
    op.drop_column("subscriptions", "service_code")
