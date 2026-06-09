"""Billing system foundation — per-currency prices, wallet ledger, billing settings, invoice lifecycle.

Phase 1 of the VoxBulk billing overhaul:
- plan_prices: explicit per-currency plan pricing (no FX conversion)
- pricing_currency_settings: per-currency service unit rates
- wallet_transactions: append-only wallet ledger (Stripe/Airwallex top-ups, launch debits, refunds)
- billing_settings: company / VAT / invoice numbering singleton
- billing_invoices: due dates, dispute flag, DD recovery state, order linkage
- subscriptions: GoCardless mandate tracking + first payment marker
- organisations: fixed billing currency + credit limit
- service_orders: launch billing breakdown snapshot
- org_usage_periods: 100% usage warning marker
- credit_notes: refund / correction documents
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0109_billing_system_foundation"
down_revision = "0108_wa_template_customer_description"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan_prices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=False, index=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("monthly_price_minor", sa.Integer(), nullable=True),
        sa.Column("per_min_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_per_min_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("plan_id", "currency", name="uq_plan_price_plan_currency"),
    )

    op.create_table(
        "pricing_currency_settings",
        sa.Column("currency", sa.String(length=3), primary_key=True),
        sa.Column("connection_fee_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interview_per_min_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wa_package_fee_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wa_extra_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cv_scan_fee_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False, index=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="GBP"),
        sa.Column("balance_after_minor", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="succeeded"),
        sa.Column("provider", sa.String(length=30), nullable=True),
        sa.Column("provider_reference", sa.String(length=128), nullable=True, index=True),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("order_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("invoice_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "billing_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_name", sa.String(length=255), nullable=False, server_default="VoxBulk Ltd"),
        sa.Column("company_address", sa.Text(), nullable=True),
        sa.Column("company_email", sa.String(length=320), nullable=True),
        sa.Column("company_phone", sa.String(length=64), nullable=True),
        sa.Column("vat_number", sa.String(length=40), nullable=True),
        sa.Column("vat_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("invoice_prefix", sa.String(length=16), nullable=False, server_default="INV"),
        sa.Column("invoice_next_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("invoice_due_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "credit_notes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False, index=True),
        sa.Column("invoice_id", sa.String(length=36), sa.ForeignKey("billing_invoices.id"), nullable=True, index=True),
        sa.Column("credit_note_number", sa.String(length=32), nullable=True, unique=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="GBP"),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="issued"),
        sa.Column("refund_method", sa.String(length=30), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.add_column("billing_invoices", sa.Column("due_date", sa.DateTime(), nullable=True))
    op.add_column("billing_invoices", sa.Column("disputed", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("billing_invoices", sa.Column("dispute_note", sa.Text(), nullable=True))
    op.add_column("billing_invoices", sa.Column("dd_payment_id", sa.String(length=128), nullable=True))
    op.add_column("billing_invoices", sa.Column("dd_status", sa.String(length=40), nullable=True))
    op.add_column("billing_invoices", sa.Column("dd_retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("billing_invoices", sa.Column("dd_next_retry_at", sa.DateTime(), nullable=True))
    op.add_column("billing_invoices", sa.Column("order_id", sa.String(length=36), nullable=True))
    op.add_column("billing_invoices", sa.Column("kind", sa.String(length=40), nullable=True))

    op.add_column("subscriptions", sa.Column("mandate_id", sa.String(length=128), nullable=True))
    op.add_column("subscriptions", sa.Column("mandate_status", sa.String(length=40), nullable=True))
    op.add_column("subscriptions", sa.Column("first_payment_at", sa.DateTime(), nullable=True))
    op.add_column("subscriptions", sa.Column("cancelled_at", sa.DateTime(), nullable=True))

    op.add_column("organisations", sa.Column("billing_currency", sa.String(length=3), nullable=True))
    op.add_column("organisations", sa.Column("credit_limit_minor", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("service_orders", sa.Column("launch_billing_json", sa.Text(), nullable=True))

    op.add_column("org_usage_periods", sa.Column("warned_at_100", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("org_usage_periods", "warned_at_100")
    op.drop_column("service_orders", "launch_billing_json")
    op.drop_column("organisations", "credit_limit_minor")
    op.drop_column("organisations", "billing_currency")
    op.drop_column("subscriptions", "cancelled_at")
    op.drop_column("subscriptions", "first_payment_at")
    op.drop_column("subscriptions", "mandate_status")
    op.drop_column("subscriptions", "mandate_id")
    for col in (
        "kind",
        "order_id",
        "dd_next_retry_at",
        "dd_retry_count",
        "dd_status",
        "dd_payment_id",
        "dispute_note",
        "disputed",
        "due_date",
    ):
        op.drop_column("billing_invoices", col)
    op.drop_table("credit_notes")
    op.drop_table("billing_settings")
    op.drop_table("wallet_transactions")
    op.drop_table("pricing_currency_settings")
    op.drop_table("plan_prices")
