"""Lead sales call outcomes and transcript.

Revision ID: 0042_lead_sales_outcomes
Revises: 0041_lead_sales
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042_lead_sales_outcomes"
down_revision = "0041_lead_sales"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lead_sales_tasks", sa.Column("telnyx_conversation_id", sa.String(length=64), nullable=True))
    op.add_column("lead_sales_tasks", sa.Column("sales_transcript_text", sa.Text(), nullable=True))
    op.add_column("lead_sales_tasks", sa.Column("outcome_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_sales_tasks", "outcome_json")
    op.drop_column("lead_sales_tasks", "sales_transcript_text")
    op.drop_column("lead_sales_tasks", "telnyx_conversation_id")
