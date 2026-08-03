"""0217 — Sales Hub redesign: benefits/tiers/terms on sales_reps + hub invoices.

Revision ID: 0217_sales_hub_partner_redesign
Revises: 0216_support_mailbox_settings

MySQL note: FK to sales_reps.id must match that column's charset/collation
(error 3780 if the new table inherits a different schema default).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0217_sales_hub_partner_redesign"
down_revision = "0216_support_mailbox_settings"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _sales_reps_id_collation() -> str | None:
    bind = op.get_bind()
    try:
        return bind.execute(
            sa.text(
                "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'sales_reps' AND COLUMN_NAME = 'id' "
                "LIMIT 1"
            )
        ).scalar()
    except Exception:
        return None


def upgrade() -> None:
    existing_rep_cols = _column_names("sales_reps")
    if "currency" not in existing_rep_cols:
        op.add_column("sales_reps", sa.Column("currency", sa.String(length=3), nullable=True))
    if "promo_benefits_json" not in existing_rep_cols:
        op.add_column("sales_reps", sa.Column("promo_benefits_json", sa.Text(), nullable=True))
    if "commission_tiers_json" not in existing_rep_cols:
        op.add_column("sales_reps", sa.Column("commission_tiers_json", sa.Text(), nullable=True))
    if "partner_terms_json" not in existing_rep_cols:
        op.add_column("sales_reps", sa.Column("partner_terms_json", sa.Text(), nullable=True))

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    collation = _sales_reps_id_collation()
    # Match referenced PK type/collation so MySQL accepts the FK (error 3780 otherwise).
    id_type = sa.String(36, collation=collation) if collation else sa.String(36)
    table_kwargs: dict = {}
    if collation:
        table_kwargs["mysql_charset"] = "utf8mb4"
        table_kwargs["mysql_collate"] = collation

    if "sales_hub_invoices" not in tables:
        op.create_table(
            "sales_hub_invoices",
            sa.Column("id", id_type, primary_key=True),
            sa.Column("sales_rep_id", id_type, nullable=False),
            sa.Column("number", sa.String(length=40), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False, server_default="commission"),
            sa.Column("customer", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("customer_tax_number", sa.String(length=80), nullable=True),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="GBP"),
            sa.Column("discount_percent", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("tax_percent", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("issued_at", sa.DateTime(), nullable=True),
            sa.Column("due_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
            sa.Column("commission_amount_minor", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "commission_approved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("reminders_sent", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("payment_provider", sa.String(length=32), nullable=True),
            sa.Column("payment_provider_ref", sa.String(length=120), nullable=True),
            sa.Column("payment_link", sa.String(length=500), nullable=True),
            sa.Column("notes", sa.String(length=500), nullable=True),
            sa.Column("reject_reason", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["sales_rep_id"], ["sales_reps.id"], name="fk_sales_hub_invoices_sales_rep_id"),
            **table_kwargs,
        )
        op.create_index("ix_sales_hub_invoices_sales_rep_id", "sales_hub_invoices", ["sales_rep_id"])
        op.create_index("ix_sales_hub_invoices_number", "sales_hub_invoices", ["number"], unique=True)
        op.create_index("ix_sales_hub_invoices_kind", "sales_hub_invoices", ["kind"])
        op.create_index("ix_sales_hub_invoices_status", "sales_hub_invoices", ["status"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "sales_hub_invoice_items" not in tables:
        inv_id_type = id_type
        # Match parent invoice id collation if the invoices table already existed from a partial run.
        try:
            parent_collation = op.get_bind().execute(
                sa.text(
                    "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = 'sales_hub_invoices' AND COLUMN_NAME = 'id' "
                    "LIMIT 1"
                )
            ).scalar()
            if parent_collation:
                inv_id_type = sa.String(36, collation=parent_collation)
                table_kwargs = {"mysql_charset": "utf8mb4", "mysql_collate": parent_collation}
        except Exception:
            pass

        op.create_table(
            "sales_hub_invoice_items",
            sa.Column("id", inv_id_type, primary_key=True),
            sa.Column("invoice_id", inv_id_type, nullable=False),
            sa.Column("service_id", sa.String(length=40), nullable=True),
            sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("unit_price_minor", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["invoice_id"], ["sales_hub_invoices.id"], name="fk_sales_hub_invoice_items_invoice_id"
            ),
            **table_kwargs,
        )
        op.create_index("ix_sales_hub_invoice_items_invoice_id", "sales_hub_invoice_items", ["invoice_id"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "sales_hub_invoice_items" in tables:
        op.drop_table("sales_hub_invoice_items")
    if "sales_hub_invoices" in tables:
        op.drop_table("sales_hub_invoices")
    existing = _column_names("sales_reps")
    for col in ("partner_terms_json", "commission_tiers_json", "promo_benefits_json", "currency"):
        if col in existing:
            op.drop_column("sales_reps", col)
