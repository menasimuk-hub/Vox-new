"""Interview booking tokens for public candidate scheduling."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0076_interview_booking_tokens"
down_revision = "0075_plan_per_min_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "interview_booking_tokens" in insp.get_table_names():
        return
    op.create_table(
        "interview_booking_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("service_orders.id"), nullable=False),
        sa.Column("recipient_id", sa.String(36), sa.ForeignKey("service_order_recipients.id"), nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("booked_start_at", sa.DateTime(), nullable=True),
        sa.Column("booked_end_at", sa.DateTime(), nullable=True),
        sa.Column("wa_sent_at", sa.DateTime(), nullable=True),
        sa.Column("wa_message_id", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("token", name="uq_interview_booking_token"),
    )
    op.create_index("ix_interview_booking_tokens_order_id", "interview_booking_tokens", ["order_id"])
    op.create_index("ix_interview_booking_tokens_recipient_id", "interview_booking_tokens", ["recipient_id"])
    op.create_index("ix_interview_booking_tokens_org_id", "interview_booking_tokens", ["org_id"])
    op.create_index("ix_interview_booking_tokens_token", "interview_booking_tokens", ["token"])


def downgrade() -> None:
    op.drop_table("interview_booking_tokens")
