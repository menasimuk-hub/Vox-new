"""Account deletion request queue table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0118_account_deletion_requests"
down_revision = "0117_billing_finance_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_deletion_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("requested_by_email", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by_admin_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("completed_by_admin_email", sa.String(length=320), nullable=True),
        sa.Column("support_ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_deletion_requests_org_id", "account_deletion_requests", ["org_id"])
    op.create_index("ix_account_deletion_requests_status", "account_deletion_requests", ["status"])
    op.create_index("ix_account_deletion_requests_requested_at", "account_deletion_requests", ["requested_at"])
    op.create_index(
        "ix_account_deletion_requests_requested_by_user_id",
        "account_deletion_requests",
        ["requested_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_deletion_requests_requested_by_user_id", table_name="account_deletion_requests")
    op.drop_index("ix_account_deletion_requests_requested_at", table_name="account_deletion_requests")
    op.drop_index("ix_account_deletion_requests_status", table_name="account_deletion_requests")
    op.drop_index("ix_account_deletion_requests_org_id", table_name="account_deletion_requests")
    op.drop_table("account_deletion_requests")
