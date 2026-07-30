"""0213 — Smart Card QR foundation tables + subscriptions.seat_quantity.

Revision ID: 0213_smart_card_qr_foundation
Revises: 0212_expo_wizard_upgrades
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0213_smart_card_qr_foundation"
down_revision = "0212_expo_wizard_upgrades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("seat_quantity", sa.Integer(), nullable=True))

    op.create_table(
        "smart_card_mailbox_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mailbox_email", sa.String(length=320), nullable=False, server_default="smartqr@voxbulk.com"),
        sa.Column("from_name", sa.String(length=255), nullable=False, server_default="VOXBULK Smart Card QR"),
        sa.Column("smtp_username", sa.String(length=255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "smart_card_packages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("monthly_unit_hint_usd_cents", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id"),
    )
    op.create_index("ix_smart_card_packages_plan_id", "smart_card_packages", ["plan_id"])
    op.create_index("ix_smart_card_packages_tier", "smart_card_packages", ["tier"])

    op.create_table(
        "smart_card_question_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("question_key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="selectable"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_key"),
    )
    op.create_index("ix_smart_card_question_templates_question_key", "smart_card_question_templates", ["question_key"])

    op.create_table(
        "smart_card_companies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("website", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("products_summary", sa.Text(), nullable=True),
        sa.Column("pricing_notes", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("brand_defaults_json", sa.Text(), nullable=True),
        sa.Column("question_config_json", sa.Text(), nullable=True),
        sa.Column("preview_tests_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id"),
    )
    op.create_index("ix_smart_card_companies_org_id", "smart_card_companies", ["org_id"])

    op.create_table(
        "smart_card_categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_card_categories_org_id", "smart_card_categories", ["org_id"])

    op.create_table(
        "smart_card_products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("match_keywords", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["smart_card_categories.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_card_products_org_id", "smart_card_products", ["org_id"])
    op.create_index("ix_smart_card_products_category_id", "smart_card_products", ["category_id"])

    op.create_table(
        "smart_card_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=True),
        sa.Column("category_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="pdf"),
        sa.Column("purpose", sa.String(length=32), nullable=False, server_default="catalogue"),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("match_keywords", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["smart_card_categories.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["smart_card_products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_card_assets_org_id", "smart_card_assets", ["org_id"])
    op.create_index("ix_smart_card_assets_product_id", "smart_card_assets", ["product_id"])
    op.create_index("ix_smart_card_assets_category_id", "smart_card_assets", ["category_id"])

    op.create_table(
        "smart_card_representatives",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("website", sa.String(length=512), nullable=True),
        sa.Column("social_links_json", sa.Text(), nullable=True),
        sa.Column("mobile", sa.String(length=64), nullable=True),
        sa.Column("landline", sa.String(length=64), nullable=True),
        sa.Column("extension", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.Column("qr_token", sa.String(length=64), nullable=False),
        sa.Column("qr_fg_color", sa.String(length=16), nullable=False, server_default="000000"),
        sa.Column("qr_bg_color", sa.String(length=16), nullable=False, server_default="ffffff"),
        sa.Column("qr_transparent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("scan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linked_user_id", sa.String(length=36), nullable=True),
        sa.Column("invite_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["linked_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("qr_token"),
    )
    op.create_index("ix_smart_card_representatives_org_id", "smart_card_representatives", ["org_id"])
    op.create_index("ix_smart_card_representatives_email", "smart_card_representatives", ["email"])
    op.create_index("ix_smart_card_representatives_qr_token", "smart_card_representatives", ["qr_token"])
    op.create_index("ix_smart_card_representatives_status", "smart_card_representatives", ["status"])
    op.create_index("ix_smart_card_representatives_linked_user_id", "smart_card_representatives", ["linked_user_id"])

    op.create_table(
        "smart_card_representative_products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("representative_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["smart_card_products.id"]),
        sa.ForeignKeyConstraint(["representative_id"], ["smart_card_representatives.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("representative_id", "product_id", name="uq_sc_rep_product"),
    )
    op.create_index("ix_smart_card_representative_products_org_id", "smart_card_representative_products", ["org_id"])
    op.create_index(
        "ix_smart_card_representative_products_representative_id",
        "smart_card_representative_products",
        ["representative_id"],
    )
    op.create_index(
        "ix_smart_card_representative_products_product_id",
        "smart_card_representative_products",
        ["product_id"],
    )

    op.create_table(
        "smart_card_change_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("representative_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["representative_id"], ["smart_card_representatives.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_card_change_requests_org_id", "smart_card_change_requests", ["org_id"])
    op.create_index("ix_smart_card_change_requests_status", "smart_card_change_requests", ["status"])

    op.create_table(
        "smart_card_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("representative_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="web"),
        sa.Column("visitor_phone", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("current_step", sa.String(length=64), nullable=True),
        sa.Column("state_json", sa.Text(), nullable=True),
        sa.Column("is_preview", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lead_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["representative_id"], ["smart_card_representatives.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_card_sessions_org_id", "smart_card_sessions", ["org_id"])
    op.create_index("ix_smart_card_sessions_representative_id", "smart_card_sessions", ["representative_id"])
    op.create_index("ix_smart_card_sessions_status", "smart_card_sessions", ["status"])

    op.create_table(
        "smart_card_responses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("question_key", sa.String(length=64), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["smart_card_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_card_responses_org_id", "smart_card_responses", ["org_id"])
    op.create_index("ix_smart_card_responses_session_id", "smart_card_responses", ["session_id"])

    op.create_table(
        "smart_card_leads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("representative_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("visitor_phone", sa.String(length=64), nullable=True),
        sa.Column("visitor_email", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("business_card_path", sa.Text(), nullable=True),
        sa.Column("interest", sa.Text(), nullable=True),
        sa.Column("buying_timeline", sa.String(length=255), nullable=True),
        sa.Column("consent", sa.String(length=64), nullable=True),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="web"),
        sa.Column("lead_score", sa.String(length=16), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("suggested_follow_up", sa.Text(), nullable=True),
        sa.Column("follow_up_status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("assets_sent_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["representative_id"], ["smart_card_representatives.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_card_leads_org_id", "smart_card_leads", ["org_id"])
    op.create_index("ix_smart_card_leads_representative_id", "smart_card_leads", ["representative_id"])
    op.create_index("ix_smart_card_leads_lead_score", "smart_card_leads", ["lead_score"])
    op.create_index("ix_smart_card_leads_follow_up_status", "smart_card_leads", ["follow_up_status"])

    op.create_table(
        "smart_card_renewal_reminder_sends",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("window_key", sa.String(length=16), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "window_key", name="uq_sc_renewal_sub_window"),
    )
    op.create_index("ix_smart_card_renewal_reminder_sends_org_id", "smart_card_renewal_reminder_sends", ["org_id"])
    op.create_index(
        "ix_smart_card_renewal_reminder_sends_subscription_id",
        "smart_card_renewal_reminder_sends",
        ["subscription_id"],
    )

    op.create_table(
        "smart_card_voice_note_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["smart_card_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_smart_card_voice_note_jobs_org_id", "smart_card_voice_note_jobs", ["org_id"])
    op.create_index("ix_smart_card_voice_note_jobs_session_id", "smart_card_voice_note_jobs", ["session_id"])
    op.create_index("ix_smart_card_voice_note_jobs_status", "smart_card_voice_note_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("smart_card_voice_note_jobs")
    op.drop_table("smart_card_renewal_reminder_sends")
    op.drop_table("smart_card_leads")
    op.drop_table("smart_card_responses")
    op.drop_table("smart_card_sessions")
    op.drop_table("smart_card_change_requests")
    op.drop_table("smart_card_representative_products")
    op.drop_table("smart_card_representatives")
    op.drop_table("smart_card_assets")
    op.drop_table("smart_card_products")
    op.drop_table("smart_card_categories")
    op.drop_table("smart_card_companies")
    op.drop_table("smart_card_question_templates")
    op.drop_table("smart_card_packages")
    op.drop_table("smart_card_mailbox_settings")
    op.drop_column("subscriptions", "seat_quantity")
