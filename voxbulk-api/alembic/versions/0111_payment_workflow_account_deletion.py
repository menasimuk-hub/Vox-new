"""Payment workflow invoice linkage + account deletion archive fields."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0111_payment_workflow_account_deletion"
down_revision = "0110_org_control_center_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("service_orders", sa.Column("payment_invoice_id", sa.String(length=36), nullable=True))
    op.add_column("service_orders", sa.Column("payment_invoice_issued_at", sa.DateTime(), nullable=True))
    op.create_index("ix_service_orders_payment_invoice_id", "service_orders", ["payment_invoice_id"])

    op.add_column("organisations", sa.Column("deletion_status", sa.String(length=20), nullable=False, server_default="active"))
    op.add_column("organisations", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("organisations", sa.Column("anonymized_at", sa.DateTime(), nullable=True))
    op.add_column("organisations", sa.Column("deletion_requested_at", sa.DateTime(), nullable=True))
    op.create_index("ix_organisations_deletion_status", "organisations", ["deletion_status"])

    op.add_column("users", sa.Column("deletion_status", sa.String(length=20), nullable=False, server_default="active"))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("anonymized_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("deletion_requested_at", sa.DateTime(), nullable=True))
    op.create_index("ix_users_deletion_status", "users", ["deletion_status"])


def downgrade() -> None:
    op.drop_index("ix_users_deletion_status", table_name="users")
    op.drop_column("users", "deletion_requested_at")
    op.drop_column("users", "anonymized_at")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "deletion_status")

    op.drop_index("ix_organisations_deletion_status", table_name="organisations")
    op.drop_column("organisations", "deletion_requested_at")
    op.drop_column("organisations", "anonymized_at")
    op.drop_column("organisations", "deleted_at")
    op.drop_column("organisations", "deletion_status")

    op.drop_index("ix_service_orders_payment_invoice_id", table_name="service_orders")
    op.drop_column("service_orders", "payment_invoice_issued_at")
    op.drop_column("service_orders", "payment_invoice_id")
