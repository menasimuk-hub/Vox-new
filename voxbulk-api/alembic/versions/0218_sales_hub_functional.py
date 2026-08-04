"""0218 — Sales hub commission months 1–6, one-time bonus, sender emails, hub invoice email.

Revision ID: 0218_sales_hub_functional
Revises: 0217_sales_hub_partner_redesign
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0218_sales_hub_functional"
down_revision = "0217_sales_hub_partner_redesign"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _column_names("sales_reps")
    if "commission_mode" not in cols:
        op.add_column(
            "sales_reps",
            sa.Column("commission_mode", sa.String(length=40), nullable=False, server_default="commission_only"),
        )
    if "one_time_bonus_minor" not in cols:
        op.add_column(
            "sales_reps",
            sa.Column("one_time_bonus_minor", sa.Integer(), nullable=False, server_default="0"),
        )

    inv_cols = _column_names("sales_hub_invoices")
    if "customer_email" not in inv_cols:
        op.add_column(
            "sales_hub_invoices",
            sa.Column("customer_email", sa.String(length=320), nullable=True),
        )

    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "platform_sender_emails" not in insp.get_table_names():
        op.create_table(
            "platform_sender_emails",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("local_part", sa.String(length=64), nullable=False),
            sa.Column("from_name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("purpose", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("local_part", name="uq_platform_sender_local_part"),
        )
        op.create_index("ix_platform_sender_emails_local_part", "platform_sender_emails", ["local_part"])
        op.create_index("ix_platform_sender_emails_purpose", "platform_sender_emails", ["purpose"])

    # Seed sales@ if missing
    op.execute(
        sa.text(
            "INSERT INTO platform_sender_emails "
            "(id, local_part, from_name, purpose, is_active, notes, created_at, updated_at) "
            "SELECT :id, 'sales', 'Voxbulk Sales', 'sales', 1, 'Hub invoices and sales mail', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "WHERE NOT EXISTS (SELECT 1 FROM platform_sender_emails WHERE local_part = 'sales')"
        ).bindparams(id="seed-sender-sales-001")
    )
    op.execute(
        sa.text(
            "INSERT INTO platform_sender_emails "
            "(id, local_part, from_name, purpose, is_active, notes, created_at, updated_at) "
            "SELECT :id, 'noreply', 'Voxbulk', 'noreply', 1, 'Transactional no-reply', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "WHERE NOT EXISTS (SELECT 1 FROM platform_sender_emails WHERE local_part = 'noreply')"
        ).bindparams(id="seed-sender-noreply-001")
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "platform_sender_emails" in insp.get_table_names():
        op.drop_table("platform_sender_emails")
    inv_cols = _column_names("sales_hub_invoices")
    if "customer_email" in inv_cols:
        op.drop_column("sales_hub_invoices", "customer_email")
    cols = _column_names("sales_reps")
    if "one_time_bonus_minor" in cols:
        op.drop_column("sales_reps", "one_time_bonus_minor")
    if "commission_mode" in cols:
        op.drop_column("sales_reps", "commission_mode")
