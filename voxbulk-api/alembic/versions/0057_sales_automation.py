"""Sales WhatsApp automation — conversation states + templates.

Revision ID: 0057_sales_automation
Revises: 0056_usage_metering_templates
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0057_sales_automation"
down_revision = "0056_usage_metering_templates"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    if not _has_table("sales_conversation_states"):
        op.create_table(
            "sales_conversation_states",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("lead_sales_task_id", sa.String(length=36), sa.ForeignKey("lead_sales_tasks.id"), nullable=False),
            sa.Column("promo_offer_id", sa.String(length=36), sa.ForeignKey("promo_offers.id"), nullable=True),
            sa.Column("prospect_phone", sa.String(length=40), nullable=True),
            sa.Column("prospect_email", sa.String(length=320), nullable=True),
            sa.Column("stage", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("automation_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("opt_in_sent_at", sa.DateTime(), nullable=True),
            sa.Column("offer_sent_at", sa.DateTime(), nullable=True),
            sa.Column("followup_due_at", sa.DateTime(), nullable=True),
            sa.Column("followup_sent_at", sa.DateTime(), nullable=True),
            sa.Column("last_inbound_at", sa.DateTime(), nullable=True),
            sa.Column("last_outbound_at", sa.DateTime(), nullable=True),
            sa.Column("last_inbound_body", sa.Text(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("meta_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_sales_conversation_states_task_id", "sales_conversation_states", ["lead_sales_task_id"])
        op.create_index("ix_sales_conversation_states_phone", "sales_conversation_states", ["prospect_phone"])
        op.create_index("ix_sales_conversation_states_promo_id", "sales_conversation_states", ["promo_offer_id"])

    if not _has_column("lead_sales_tasks", "automation_paused"):
        op.add_column("lead_sales_tasks", sa.Column("automation_paused", sa.Boolean(), nullable=False, server_default=sa.false()))

    if not _has_column("lead_sales_settings", "sales_automation_enabled"):
        op.add_column("lead_sales_settings", sa.Column("sales_automation_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    if not _has_column("lead_sales_settings", "sales_auto_plan_code"):
        op.add_column("lead_sales_settings", sa.Column("sales_auto_plan_code", sa.String(length=64), nullable=False, server_default="dental_1"))
    if not _has_column("lead_sales_settings", "sales_auto_trial_days"):
        op.add_column("lead_sales_settings", sa.Column("sales_auto_trial_days", sa.Integer(), nullable=False, server_default="15"))
    if not _has_column("lead_sales_settings", "sales_followup_days"):
        op.add_column("lead_sales_settings", sa.Column("sales_followup_days", sa.Integer(), nullable=False, server_default="7"))

    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "whatsapp_templates" in insp.get_table_names():
        from app.data.sales_automation_defaults import (
            SALES_OFFER_FOLLOWUP_WHATSAPP_BODY,
            SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY,
            SALES_OPT_IN_WHATSAPP_BODY,
        )

        seeds = (
            ("sales_opt_in", "Sales opt-in (reply SEND OFFER)", SALES_OPT_IN_WHATSAPP_BODY),
            ("sales_offer_followup", "Sales offer 7-day follow-up", SALES_OFFER_FOLLOWUP_WHATSAPP_BODY),
            ("sales_offer_keyword_confirm", "Sales offer keyword confirmation", SALES_OFFER_KEYWORD_CONFIRM_WHATSAPP_BODY),
        )
        for key, name, body in seeds:
            exists = bind.execute(
                sa.text("SELECT 1 FROM whatsapp_templates WHERE template_key = :key LIMIT 1"),
                {"key": key},
            ).scalar()
            if not exists:
                bind.execute(
                    sa.text(
                        "INSERT INTO whatsapp_templates (template_key, name, body, is_enabled, created_at, updated_at) "
                        "VALUES (:key, :name, :body, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"key": key, "name": name, "body": body},
                )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM whatsapp_templates WHERE template_key IN "
            "('sales_opt_in', 'sales_offer_followup', 'sales_offer_keyword_confirm')"
        )
    )
    if _has_column("lead_sales_settings", "sales_followup_days"):
        op.drop_column("lead_sales_settings", "sales_followup_days")
    if _has_column("lead_sales_settings", "sales_auto_trial_days"):
        op.drop_column("lead_sales_settings", "sales_auto_trial_days")
    if _has_column("lead_sales_settings", "sales_auto_plan_code"):
        op.drop_column("lead_sales_settings", "sales_auto_plan_code")
    if _has_column("lead_sales_settings", "sales_automation_enabled"):
        op.drop_column("lead_sales_settings", "sales_automation_enabled")
    if _has_column("lead_sales_tasks", "automation_paused"):
        op.drop_column("lead_sales_tasks", "automation_paused")
    op.drop_index("ix_sales_conversation_states_promo_id", table_name="sales_conversation_states")
    op.drop_index("ix_sales_conversation_states_phone", table_name="sales_conversation_states")
    op.drop_index("ix_sales_conversation_states_task_id", table_name="sales_conversation_states")
    op.drop_table("sales_conversation_states")
