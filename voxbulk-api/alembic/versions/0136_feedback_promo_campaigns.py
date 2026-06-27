"""Feedback promo campaigns — Task 5 send/pay-then-run."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0136_feedback_promo_campaigns"
down_revision = "0135_feedback_pricing_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_promo_campaigns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False, index=True),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("template_name", sa.String(128), nullable=False),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column("variables_json", sa.Text(), nullable=True),
        sa.Column("use_opt_in_audience", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("manual_recipients_json", sa.Text(), nullable=True),
        sa.Column("opt_in_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("manual_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="GBP"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("billing_invoices.id"), nullable=True, index=True),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("yes_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("no_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("launched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("feedback_promo_campaigns")
