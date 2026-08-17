"""0256 — Billing audit: one live sub per org+service, invoice snapshots, CN sequence.

Revision ID: 0256_billing_audit_hardening
Revises: 0255_seed_catalog_plan_unit_rates
Create Date: 2026-08-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0256_billing_audit_hardening"
down_revision = "0255_seed_catalog_plan_unit_rates"
branch_labels = None
depends_on = None

LIVE = ("active", "trial", "past_due", "suspended", "pending_first_payment", "pending_payment")


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("live_slot", sa.Integer(), nullable=True))
    op.add_column("subscriptions", sa.Column("last_advanced_payment_id", sa.String(128), nullable=True))
    op.add_column("billing_settings", sa.Column("credit_note_next_number", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("billing_invoices", sa.Column("issued_company_name", sa.String(255), nullable=True))
    op.add_column("billing_invoices", sa.Column("issued_company_address", sa.Text(), nullable=True))
    op.add_column("billing_invoices", sa.Column("issued_customer_name", sa.String(255), nullable=True))
    op.add_column("billing_invoices", sa.Column("issued_customer_address", sa.Text(), nullable=True))

    conn = op.get_bind()
    live_list = ", ".join(f"'{s}'" for s in LIVE)
    rows = conn.execute(
        sa.text(
            f"""
            SELECT id, org_id, service_code, status, updated_at, created_at
            FROM subscriptions
            WHERE LOWER(COALESCE(status, '')) IN ({live_list})
            ORDER BY org_id, service_code, updated_at DESC, created_at DESC
            """
        )
    ).fetchall()
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.org_id), str(row.service_code or "voxbulk"))
        if key in seen:
            conn.execute(
                sa.text(
                    "UPDATE subscriptions SET status = 'cancelled', live_slot = NULL "
                    "WHERE id = :id"
                ),
                {"id": row.id},
            )
        else:
            seen.add(key)
            conn.execute(
                sa.text("UPDATE subscriptions SET live_slot = 1 WHERE id = :id"),
                {"id": row.id},
            )

    op.create_index(
        "uq_subscriptions_org_service_live",
        "subscriptions",
        ["org_id", "service_code", "live_slot"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_subscriptions_org_service_live", table_name="subscriptions")
    op.drop_column("billing_invoices", "issued_customer_address")
    op.drop_column("billing_invoices", "issued_customer_name")
    op.drop_column("billing_invoices", "issued_company_address")
    op.drop_column("billing_invoices", "issued_company_name")
    op.drop_column("billing_settings", "credit_note_next_number")
    op.drop_column("subscriptions", "last_advanced_payment_id")
    op.drop_column("subscriptions", "live_slot")
