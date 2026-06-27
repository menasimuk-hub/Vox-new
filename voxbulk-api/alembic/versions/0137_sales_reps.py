"""Salesman feature — Task 8: sales reps, their customers, and commission ledger."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0137_sales_reps"
down_revision = "0136_feedback_promo_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sales_reps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("promo_code", sa.String(32), nullable=False, unique=True, index=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("caller_id", sa.String(40), nullable=True),
        sa.Column("commission_kind", sa.String(32), nullable=False, server_default="subscription"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "sales_customers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sales_rep_id", sa.String(36), sa.ForeignKey("sales_reps.id"), nullable=False, index=True),
        sa.Column("full_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("country", sa.String(120), nullable=True),
        sa.Column("mobile", sa.String(40), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("business_type", sa.String(80), nullable=True),
        sa.Column("branches", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("contact_person", sa.String(200), nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=True, index=True),
        sa.Column("offer_details", sa.String(255), nullable=True),
        sa.Column("offer_sent_at", sa.DateTime(), nullable=True),
        sa.Column("offer_log_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="lead"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "sales_commissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sales_rep_id", sa.String(36), sa.ForeignKey("sales_reps.id"), nullable=False, index=True),
        sa.Column("sales_customer_id", sa.String(36), sa.ForeignKey("sales_customers.id"), nullable=True, index=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False, index=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("billing_invoices.id"), nullable=True, index=True),
        sa.Column("subscription_id", sa.String(36), nullable=True, index=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="GBP"),
        sa.Column("kind", sa.String(24), nullable=False, server_default="monthly_2nd"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sales_commissions")
    op.drop_table("sales_customers")
    op.drop_table("sales_reps")
