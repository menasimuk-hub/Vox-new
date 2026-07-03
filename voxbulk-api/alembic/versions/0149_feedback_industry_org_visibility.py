"""Feedback industry visibility (all orgs vs selected orgs)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0149_feedback_industry_org_visibility"
down_revision = "0148_org_billing_payment_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedback_industries",
        sa.Column("visibility_mode", sa.String(length=20), nullable=False, server_default="all"),
    )
    op.create_table(
        "feedback_industry_organisations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("industry_id", sa.String(length=36), sa.ForeignKey("feedback_industries.id"), nullable=False, index=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("industry_id", "org_id", name="uq_feedback_industry_org"),
    )


def downgrade() -> None:
    op.drop_table("feedback_industry_organisations")
    op.drop_column("feedback_industries", "visibility_mode")
