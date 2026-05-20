"""platform services catalog and service orders

Revision ID: 0045_platform_services_orders
Revises: 0044_lead_sales_kb_prompt
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0045_platform_services_orders"
down_revision = "0044_lead_sales_kb_prompt"
branch_labels = None
depends_on = None

NOW = datetime.utcnow()


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "platform_services" not in tables:
        op.create_table(
            "platform_services",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("service_kind", sa.String(length=32), nullable=False, server_default="order"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("100")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_platform_services_code"),
        )
        op.create_index("ix_platform_services_code", "platform_services", ["code"])

    if "service_pricing_rules" not in tables:
        op.create_table(
            "service_pricing_rules",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("service_id", sa.String(length=36), nullable=False),
            sa.Column("channel", sa.String(length=32), nullable=False, server_default="default"),
            sa.Column("rule_type", sa.String(length=32), nullable=False),
            sa.Column("label", sa.String(length=160), nullable=False),
            sa.Column("base_fee_pence", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("unit_price_pence", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("bundle_size", sa.Integer(), nullable=True),
            sa.Column("bundle_price_pence", sa.Integer(), nullable=True),
            sa.Column("included_units", sa.Integer(), nullable=True),
            sa.Column("overage_unit_price_pence", sa.Integer(), nullable=True),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="GBP"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("100")),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["service_id"], ["platform_services.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_service_pricing_rules_service_id", "service_pricing_rules", ["service_id"])

    if "service_orders" not in tables:
        op.create_table(
            "service_orders",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("org_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("service_code", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("payment_status", sa.String(length=32), nullable=False, server_default="unpaid"),
            sa.Column("recipient_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("quote_total_pence", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("quote_breakdown_json", sa.Text(), nullable=True),
            sa.Column("config_json", sa.Text(), nullable=True),
            sa.Column("run_mode", sa.String(length=16), nullable=False, server_default="manual"),
            sa.Column("scheduled_start_at", sa.DateTime(), nullable=True),
            sa.Column("scheduled_end_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("payment_method", sa.String(length=32), nullable=True),
            sa.Column("payment_note", sa.Text(), nullable=True),
            sa.Column("admin_decision_note", sa.Text(), nullable=True),
            sa.Column("report_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_service_orders_org_id", "service_orders", ["org_id"])
        op.create_index("ix_service_orders_service_code", "service_orders", ["service_code"])
        op.create_index("ix_service_orders_status", "service_orders", ["status"])
        op.create_index("ix_service_orders_payment_status", "service_orders", ["payment_status"])

    if "service_order_recipients" not in tables:
        op.create_table(
            "service_order_recipients",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("order_id", sa.String(length=36), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("phone", sa.String(length=64), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["service_orders.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_service_order_recipients_order_id", "service_order_recipients", ["order_id"])

    _seed_defaults(bind)


def _seed_defaults(bind) -> None:
    existing = bind.execute(sa.text("SELECT COUNT(*) FROM platform_services")).scalar_one()
    if int(existing or 0) > 0:
        return

    survey_id = str(uuid.uuid4())
    interview_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            """
            INSERT INTO platform_services (id, code, name, description, service_kind, is_active, sort_order, created_at, updated_at)
            VALUES
            (:survey_id, 'survey', 'Survey', 'Bulk WhatsApp + AI call surveys with smart reporting.', 'order', 1, 10, :now, :now),
            (:interview_id, 'interview', 'Interview', 'AI phone or Zoom interview screening campaigns.', 'order', 1, 20, :now, :now)
            """
        ),
        {"survey_id": survey_id, "interview_id": interview_id, "now": NOW},
    )
    rules = [
        (survey_id, "base", "flat_per_order", "Survey setup fee", 500, 0, None, None),
        (survey_id, "whatsapp", "bundle", "WhatsApp — 100 contacts", 0, 0, 100, 1500),
        (survey_id, "call", "per_person", "AI call — per contact", 0, 18, None, None),
        (interview_id, "ai_call", "per_person", "Interview AI call — per person", 0, 350, None, None),
        (interview_id, "zoom", "per_person", "Interview Zoom — per person", 0, 500, None, None),
    ]
    for service_id, channel, rule_type, label, base_fee, unit_price, bundle_size, bundle_price in rules:
        bind.execute(
            sa.text(
                """
                INSERT INTO service_pricing_rules
                (id, service_id, channel, rule_type, label, base_fee_pence, unit_price_pence, bundle_size, bundle_price_pence,
                 included_units, overage_unit_price_pence, currency, is_active, sort_order, notes, created_at, updated_at)
                VALUES
                (:id, :service_id, :channel, :rule_type, :label, :base_fee, :unit_price, :bundle_size, :bundle_price,
                 NULL, NULL, 'GBP', 1, 100, NULL, :now, :now)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "service_id": service_id,
                "channel": channel,
                "rule_type": rule_type,
                "label": label,
                "base_fee": base_fee,
                "unit_price": unit_price,
                "bundle_size": bundle_size,
                "bundle_price": bundle_price,
                "now": NOW,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_service_order_recipients_order_id", table_name="service_order_recipients")
    op.drop_table("service_order_recipients")
    op.drop_index("ix_service_orders_payment_status", table_name="service_orders")
    op.drop_index("ix_service_orders_status", table_name="service_orders")
    op.drop_index("ix_service_orders_service_code", table_name="service_orders")
    op.drop_index("ix_service_orders_org_id", table_name="service_orders")
    op.drop_table("service_orders")
    op.drop_index("ix_service_pricing_rules_service_id", table_name="service_pricing_rules")
    op.drop_table("service_pricing_rules")
    op.drop_index("ix_platform_services_code", table_name="platform_services")
    op.drop_table("platform_services")
