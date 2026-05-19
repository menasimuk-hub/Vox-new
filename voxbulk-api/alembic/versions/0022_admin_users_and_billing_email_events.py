"""admin users + billing email event tables

Revision ID: 0022_admin_users_billing_events
Revises: 0021_password_reset_tokens
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0022_admin_users_billing_events"
down_revision = "0021_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_event_id", sa.String(length=128), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("client_email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("emailed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_payment_event_provider_external"),
    )
    op.create_index("ix_payment_events_provider", "payment_events", ["provider"], unique=False)
    op.create_index("ix_payment_events_external_event_id", "payment_events", ["external_event_id"], unique=False)
    op.create_index("ix_payment_events_org_id", "payment_events", ["org_id"], unique=False)
    op.create_index("ix_payment_events_status", "payment_events", ["status"], unique=False)

    op.create_table(
        "billing_invoices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_invoice_id", sa.String(length=128), nullable=False),
        sa.Column("client_email", sa.String(length=320), nullable=False),
        sa.Column("amount_gbp_pence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="GBP"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="issued"),
        sa.Column("emailed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("provider", "external_invoice_id", name="uq_invoice_provider_external_id"),
    )
    op.create_index("ix_billing_invoices_org_id", "billing_invoices", ["org_id"], unique=False)
    op.create_index("ix_billing_invoices_provider", "billing_invoices", ["provider"], unique=False)
    op.create_index("ix_billing_invoices_external_invoice_id", "billing_invoices", ["external_invoice_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_billing_invoices_external_invoice_id", table_name="billing_invoices")
    op.drop_index("ix_billing_invoices_provider", table_name="billing_invoices")
    op.drop_index("ix_billing_invoices_org_id", table_name="billing_invoices")
    op.drop_table("billing_invoices")

    op.drop_index("ix_payment_events_status", table_name="payment_events")
    op.drop_index("ix_payment_events_org_id", table_name="payment_events")
    op.drop_index("ix_payment_events_external_event_id", table_name="payment_events")
    op.drop_index("ix_payment_events_provider", table_name="payment_events")
    op.drop_table("payment_events")

    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_table("admin_users")

