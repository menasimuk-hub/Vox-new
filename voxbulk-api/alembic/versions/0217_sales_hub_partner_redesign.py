"""0217 — Sales Hub redesign: benefits/tiers/terms on sales_reps + hub invoices.

Revision ID: 0217_sales_hub_partner_redesign
Revises: 0216_support_mailbox_settings
"""

from alembic import op
import sqlalchemy as sa


revision = "0217_sales_hub_partner_redesign"
down_revision = "0216_support_mailbox_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sales_reps") as batch:
        batch.add_column(sa.Column("currency", sa.String(length=3), nullable=True))
        batch.add_column(sa.Column("promo_benefits_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("commission_tiers_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("partner_terms_json", sa.Text(), nullable=True))

    op.create_table(
        "sales_hub_invoices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sales_rep_id", sa.String(length=36), sa.ForeignKey("sales_reps.id"), nullable=False, index=True),
        sa.Column("number", sa.String(length=40), nullable=False, unique=True, index=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="commission", index=True),
        sa.Column("customer", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("customer_tax_number", sa.String(length=80), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="GBP"),
        sa.Column("discount_percent", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("tax_percent", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("issued_at", sa.DateTime(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new", index=True),
        sa.Column("commission_amount_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commission_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reminders_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payment_provider", sa.String(length=32), nullable=True),
        sa.Column("payment_provider_ref", sa.String(length=120), nullable=True),
        sa.Column("payment_link", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("reject_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "sales_hub_invoice_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "invoice_id",
            sa.String(length=36),
            sa.ForeignKey("sales_hub_invoices.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("service_id", sa.String(length=40), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sales_hub_invoice_items")
    op.drop_table("sales_hub_invoices")
    with op.batch_alter_table("sales_reps") as batch:
        batch.drop_column("partner_terms_json")
        batch.drop_column("commission_tiers_json")
        batch.drop_column("promo_benefits_json")
        batch.drop_column("currency")
