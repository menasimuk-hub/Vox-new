"""Sales funnel: add stage timestamps + interested flag to sales_customers."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0144_sales_customer_funnel_fields"
down_revision = "0143_subscription_billing_interval"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        return any(col["name"] == column for col in inspector.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    if not _has_column("sales_customers", "demo_wa_sent_at"):
        op.add_column("sales_customers", sa.Column("demo_wa_sent_at", sa.DateTime(), nullable=True))
    if not _has_column("sales_customers", "demo_call_sent_at"):
        op.add_column("sales_customers", sa.Column("demo_call_sent_at", sa.DateTime(), nullable=True))
    if not _has_column("sales_customers", "interested"):
        op.add_column(
            "sales_customers",
            sa.Column("interested", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    if not _has_column("sales_customers", "interested_at"):
        op.add_column("sales_customers", sa.Column("interested_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if _has_column("sales_customers", "interested_at"):
        op.drop_column("sales_customers", "interested_at")
    if _has_column("sales_customers", "interested"):
        op.drop_column("sales_customers", "interested")
    if _has_column("sales_customers", "demo_call_sent_at"):
        op.drop_column("sales_customers", "demo_call_sent_at")
    if _has_column("sales_customers", "demo_wa_sent_at"):
        op.drop_column("sales_customers", "demo_wa_sent_at")
