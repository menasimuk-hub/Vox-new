"""0162 — survey_ai_follow_up_jobs for WA Survey AI voice callbacks."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0162_survey_ai_follow_up_jobs"
down_revision = "0161_merge_rates_and_followup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "survey_ai_follow_up_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("service_orders.id"), nullable=False),
        sa.Column(
            "recipient_id",
            sa.String(length=36),
            sa.ForeignKey("service_order_recipients.id"),
            nullable=False,
        ),
        sa.Column("visitor_phone", sa.String(length=64), nullable=False),
        sa.Column("business_context", sa.Text(), nullable=True),
        sa.Column("promo_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("promo_code", sa.String(length=64), nullable=True),
        sa.Column("promo_description", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column("call_id", sa.String(length=128), nullable=True),
        sa.Column("outcome_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("recipient_id", name="uq_survey_ai_follow_up_recipient"),
    )
    op.create_index("ix_survey_ai_follow_up_jobs_org_id", "survey_ai_follow_up_jobs", ["org_id"])
    op.create_index("ix_survey_ai_follow_up_jobs_order_id", "survey_ai_follow_up_jobs", ["order_id"])
    op.create_index("ix_survey_ai_follow_up_jobs_recipient_id", "survey_ai_follow_up_jobs", ["recipient_id"])
    op.create_index("ix_survey_ai_follow_up_jobs_scheduled_at", "survey_ai_follow_up_jobs", ["scheduled_at"])


def downgrade() -> None:
    op.drop_index("ix_survey_ai_follow_up_jobs_scheduled_at", table_name="survey_ai_follow_up_jobs")
    op.drop_index("ix_survey_ai_follow_up_jobs_recipient_id", table_name="survey_ai_follow_up_jobs")
    op.drop_index("ix_survey_ai_follow_up_jobs_order_id", table_name="survey_ai_follow_up_jobs")
    op.drop_index("ix_survey_ai_follow_up_jobs_org_id", table_name="survey_ai_follow_up_jobs")
    op.drop_table("survey_ai_follow_up_jobs")
