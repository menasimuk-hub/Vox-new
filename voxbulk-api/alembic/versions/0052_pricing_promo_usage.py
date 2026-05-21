"""pricing packages, promo offers, usage wallets

Revision ID: 0052_pricing_promo_usage
Revises: 0051_legal_seed_force
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0052_pricing_promo_usage"
down_revision = "0051_legal_seed_force"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("calls_included", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("plans", sa.Column("whatsapp_included", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("plans", sa.Column("sms_included", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("plans", sa.Column("overage_per_min_pence", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("plans", sa.Column("trial_days_default", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("plans", sa.Column("service_kind", sa.String(length=32), nullable=False, server_default="dental"))

    op.create_table(
        "promo_offers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("offer_type", sa.String(length=32), nullable=False, server_default="dental_trial"),
        sa.Column("plan_code", sa.String(length=64), nullable=True),
        sa.Column("service_kind", sa.String(length=32), nullable=True),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("free_call_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("whatsapp_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sms_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_gbp_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overage_per_min_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prospect_email", sa.String(length=320), nullable=True),
        sa.Column("prospect_phone", sa.String(length=40), nullable=True),
        sa.Column("prospect_name", sa.String(length=200), nullable=True),
        sa.Column("lead_sales_task_id", sa.String(length=36), nullable=True),
        sa.Column("max_redemptions", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("redemption_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_promo_offers_code", "promo_offers", ["code"], unique=True)
    op.create_index("ix_promo_offers_lead_sales_task_id", "promo_offers", ["lead_sales_task_id"])

    op.create_table(
        "org_usage_periods",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("plan_code", sa.String(length=64), nullable=True),
        sa.Column("promo_code", sa.String(length=64), nullable=True),
        sa.Column("calls_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("whatsapp_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("whatsapp_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sms_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sms_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pack_credits_included", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pack_credits_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pack_credits_expires_at", sa.DateTime(), nullable=True),
        sa.Column("overage_per_min_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warned_at_80", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_org_usage_periods_org_id", "org_usage_periods", ["org_id"])

    op.create_table(
        "promo_redemptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("promo_offer_id", sa.String(length=36), sa.ForeignKey("promo_offers.id"), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_promo_redemptions_promo_offer_id", "promo_redemptions", ["promo_offer_id"])
    op.create_index("ix_promo_redemptions_org_id", "promo_redemptions", ["org_id"])

    op.add_column("onboarding_requests", sa.Column("promo_code", sa.String(length=64), nullable=True))
    op.add_column("lead_sales_tasks", sa.Column("offer_promo_code", sa.String(length=64), nullable=True))
    op.add_column("lead_sales_tasks", sa.Column("offer_sent_at", sa.DateTime(), nullable=True))
    op.add_column("lead_sales_tasks", sa.Column("offer_send_log_json", sa.Text(), nullable=True))

    conn = op.get_bind()
    now = datetime.utcnow()
    dental_plans = [
        {
            "code": "dental_1",
            "name": "Dental Package 1",
            "price": 19900,
            "calls": 300,
            "wa": 500,
            "sms": 300,
            "overage": 20,
            "features": ["300 AI calls / month", "500 WhatsApp / month", "300 SMS / month", "£0.20/min overage"],
        },
        {
            "code": "dental_2",
            "name": "Dental Package 2",
            "price": 29900,
            "calls": 500,
            "wa": 800,
            "sms": 600,
            "overage": 15,
            "features": ["500 AI calls / month", "800 WhatsApp / month", "600 SMS / month", "£0.15/min overage"],
        },
    ]
    for row in dental_plans:
        exists = conn.execute(sa.text("SELECT id FROM plans WHERE code = :code"), {"code": row["code"]}).fetchone()
        if exists:
            conn.execute(
                sa.text(
                    """
                    UPDATE plans SET
                      price_gbp_pence = :price,
                      calls_included = :calls,
                      whatsapp_included = :wa,
                      sms_included = :sms,
                      overage_per_min_pence = :overage,
                      trial_days_default = 15,
                      service_kind = 'dental',
                      description = :desc,
                      features_json = :features
                    WHERE code = :code
                    """
                ),
                {
                    "code": row["code"],
                    "price": row["price"],
                    "calls": row["calls"],
                    "wa": row["wa"],
                    "sms": row["sms"],
                    "overage": row["overage"],
                    "desc": row["name"],
                    "features": json.dumps(row["features"]),
                },
            )
        else:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO plans (
                      id, code, name, price_gbp_pence, interval, description, features_json,
                      calls_included, whatsapp_included, sms_included, overage_per_min_pence,
                      trial_days_default, service_kind, created_at
                    ) VALUES (
                      :id, :code, :name, :price, 'monthly', :desc, :features,
                      :calls, :wa, :sms, :overage, 15, 'dental', :now
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "code": row["code"],
                    "name": row["name"],
                    "price": row["price"],
                    "desc": row["name"],
                    "features": json.dumps(row["features"]),
                    "calls": row["calls"],
                    "wa": row["wa"],
                    "sms": row["sms"],
                    "overage": row["overage"],
                    "now": now,
                },
            )

    conn.execute(
        sa.text(
            """
            UPDATE plans SET
              calls_included = CASE code
                WHEN 'starter' THEN 100 WHEN 'practice' THEN 300 WHEN 'group' THEN 600 ELSE calls_included END,
              whatsapp_included = CASE code
                WHEN 'starter' THEN 200 WHEN 'practice' THEN 500 WHEN 'group' THEN 1000 ELSE whatsapp_included END,
              sms_included = CASE code
                WHEN 'starter' THEN 100 WHEN 'practice' THEN 300 WHEN 'group' THEN 600 ELSE sms_included END,
              overage_per_min_pence = CASE code
                WHEN 'starter' THEN 20 WHEN 'practice' THEN 20 WHEN 'group' THEN 15 ELSE overage_per_min_pence END,
              trial_days_default = CASE WHEN trial_days_default = 0 THEN 15 ELSE trial_days_default END,
              service_kind = CASE WHEN service_kind = '' OR service_kind IS NULL THEN 'dental' ELSE service_kind END
            WHERE code IN ('starter', 'practice', 'group')
            """
        )
    )


def downgrade() -> None:
    op.drop_column("lead_sales_tasks", "offer_send_log_json")
    op.drop_column("lead_sales_tasks", "offer_sent_at")
    op.drop_column("lead_sales_tasks", "offer_promo_code")
    op.drop_column("onboarding_requests", "promo_code")
    op.drop_index("ix_promo_redemptions_org_id", table_name="promo_redemptions")
    op.drop_index("ix_promo_redemptions_promo_offer_id", table_name="promo_redemptions")
    op.drop_table("promo_redemptions")
    op.drop_index("ix_org_usage_periods_org_id", table_name="org_usage_periods")
    op.drop_table("org_usage_periods")
    op.drop_index("ix_promo_offers_lead_sales_task_id", table_name="promo_offers")
    op.drop_index("ix_promo_offers_code", table_name="promo_offers")
    op.drop_table("promo_offers")
    op.drop_column("plans", "service_kind")
    op.drop_column("plans", "trial_days_default")
    op.drop_column("plans", "overage_per_min_pence")
    op.drop_column("plans", "sms_included")
    op.drop_column("plans", "whatsapp_included")
    op.drop_column("plans", "calls_included")
