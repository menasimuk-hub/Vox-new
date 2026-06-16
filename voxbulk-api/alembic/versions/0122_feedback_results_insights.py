"""Feedback results insights cache + response answer_source."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0122_feedback_results_insights"
down_revision = "0121_merge_hubspot_and_industry_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedback_responses",
        sa.Column("answer_source", sa.String(length=16), nullable=True),
    )
    op.create_table(
        "feedback_results_insights",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("location_key", sa.String(length=64), nullable=False, server_default="__all__"),
        sa.Column("fingerprint", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("themes_json", sa.Text(), nullable=True),
        sa.Column("recommendations_json", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "location_key", name="uq_feedback_insights_org_loc"),
    )
    op.create_index("ix_feedback_results_insights_org_id", "feedback_results_insights", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_results_insights_org_id", table_name="feedback_results_insights")
    op.drop_table("feedback_results_insights")
    op.drop_column("feedback_responses", "answer_source")
