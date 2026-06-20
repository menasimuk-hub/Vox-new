"""CRM deal-stage survey automation queue."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0126_crm_survey_automation_events"
down_revision = "0125_crm_synced_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_survey_automation_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_deal_id", sa.String(length=64), nullable=False),
        sa.Column("external_person_id", sa.String(length=64), nullable=True),
        sa.Column("deal_title", sa.String(length=255), nullable=True),
        sa.Column("stage_id", sa.String(length=64), nullable=True),
        sa.Column("stage_name", sa.String(length=128), nullable=True),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column("skip_reason", sa.String(length=512), nullable=True),
        sa.Column("scheduled_send_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("recipient_id", sa.String(length=36), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["service_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id",
            "provider",
            "external_deal_id",
            name="uq_crm_survey_automation_order_provider_deal",
        ),
    )
    op.create_index("ix_crm_survey_automation_events_org_id", "crm_survey_automation_events", ["org_id"])
    op.create_index("ix_crm_survey_automation_events_order_id", "crm_survey_automation_events", ["order_id"])
    op.create_index("ix_crm_survey_automation_events_provider", "crm_survey_automation_events", ["provider"])
    op.create_index("ix_crm_survey_automation_events_external_deal_id", "crm_survey_automation_events", ["external_deal_id"])
    op.create_index("ix_crm_survey_automation_events_status", "crm_survey_automation_events", ["status"])
    op.create_index("ix_crm_survey_automation_events_scheduled_send_at", "crm_survey_automation_events", ["scheduled_send_at"])
    op.create_index("ix_crm_survey_automation_events_recipient_id", "crm_survey_automation_events", ["recipient_id"])


def downgrade() -> None:
    op.drop_table("crm_survey_automation_events")
