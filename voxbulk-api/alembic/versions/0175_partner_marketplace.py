"""Alembic migration: partner marketplace tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0175_partner_marketplace"
down_revision = "0174_seo_gsc_traffic_kpis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_providers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="sandbox"),
        sa.Column("mapped_org_id", sa.String(length=36), nullable=True),
        sa.Column("result_webhook_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("webhook_secret_enc", sa.Text(), nullable=True),
        sa.Column("connection_fee_gbp", sa.Float(), nullable=False, server_default="1.5"),
        sa.Column("per_minute_gbp", sa.Float(), nullable=False, server_default="0.35"),
        sa.Column("commission_pct", sa.Float(), nullable=False, server_default="18"),
        sa.Column("est_cost_per_completed_gbp", sa.Float(), nullable=False, server_default="5"),
        # MySQL rejects DEFAULT on TEXT/BLOB — app supplies "{}" on insert.
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("last_health_at", sa.DateTime(), nullable=True),
        sa.Column("last_health_ok", sa.Boolean(), nullable=True),
        sa.Column("last_health_message", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["mapped_org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_partner_providers_key", "partner_providers", ["key"])
    op.create_index("ix_partner_providers_mapped_org_id", "partner_providers", ["mapped_org_id"])

    op.create_table(
        "partner_api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False, server_default="sandbox"),
        sa.Column("key_prefix", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["provider_id"], ["partner_providers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("ix_partner_api_keys_provider_id", "partner_api_keys", ["provider_id"])
    op.create_index("ix_partner_api_keys_key_hash", "partner_api_keys", ["key_hash"])

    op.create_table(
        "partner_screenings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.Column("partner_reference_id", sa.String(length=120), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False, server_default="sandbox"),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("recipient_id", sa.String(length=36), nullable=True),
        sa.Column("job_title", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("candidate_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("candidate_phone", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("preferred_language", sa.String(length=8), nullable=False, server_default="en"),
        # MySQL rejects DEFAULT on TEXT/BLOB — app supplies "[]" on insert.
        sa.Column("screening_questions_json", sa.Text(), nullable=False),
        sa.Column("callback_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="accepted"),
        sa.Column("screening_link", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("estimated_completion_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("candidate_score", sa.Integer(), nullable=True),
        sa.Column("result_status", sa.String(length=32), nullable=True),
        sa.Column("report_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("call_duration_minutes", sa.Float(), nullable=True),
        sa.Column("total_charge_gbp", sa.Float(), nullable=True),
        sa.Column("result_posted_at", sa.DateTime(), nullable=True),
        sa.Column("webhook_delivered_at", sa.DateTime(), nullable=True),
        sa.Column("webhook_last_error", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["partner_providers.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["service_orders.id"]),
        sa.ForeignKeyConstraint(["recipient_id"], ["service_order_recipients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_partner_screenings_provider_id", "partner_screenings", ["provider_id"])
    op.create_index("ix_partner_screenings_partner_reference_id", "partner_screenings", ["partner_reference_id"])
    op.create_index("ix_partner_screenings_org_id", "partner_screenings", ["org_id"])
    op.create_index("ix_partner_screenings_order_id", "partner_screenings", ["order_id"])
    op.create_index("ix_partner_screenings_recipient_id", "partner_screenings", ["recipient_id"])


def downgrade() -> None:
    op.drop_table("partner_screenings")
    op.drop_table("partner_api_keys")
    op.drop_table("partner_providers")
