"""AI demo invite open/click tracking columns + nullable WhatsApp."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0245_ai_demo_tracking"
down_revision = "0244_ai_demo_agent"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_table("demo_requests"):
        return
    with op.batch_alter_table("demo_requests") as batch:
        if not _has_column("demo_requests", "tracking_token"):
            batch.add_column(sa.Column("tracking_token", sa.String(64), nullable=True))
        if not _has_column("demo_requests", "email_sent_at"):
            batch.add_column(sa.Column("email_sent_at", sa.DateTime(), nullable=True))
        if not _has_column("demo_requests", "opened_at"):
            batch.add_column(sa.Column("opened_at", sa.DateTime(), nullable=True))
        if not _has_column("demo_requests", "open_count"):
            batch.add_column(sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"))
        if not _has_column("demo_requests", "link_clicked_at"):
            batch.add_column(sa.Column("link_clicked_at", sa.DateTime(), nullable=True))
        if not _has_column("demo_requests", "click_count"):
            batch.add_column(sa.Column("click_count", sa.Integer(), nullable=False, server_default="0"))
    # Make whatsapp nullable for email-only batch invites
    try:
        op.alter_column(
            "demo_requests",
            "whatsapp_e164",
            existing_type=sa.String(40),
            nullable=True,
        )
    except Exception:
        pass
    if _has_column("demo_requests", "tracking_token"):
        try:
            op.create_index("ix_demo_requests_tracking_token", "demo_requests", ["tracking_token"], unique=True)
        except Exception:
            pass


def downgrade() -> None:
    if not _has_table("demo_requests"):
        return
    try:
        op.drop_index("ix_demo_requests_tracking_token", table_name="demo_requests")
    except Exception:
        pass
    with op.batch_alter_table("demo_requests") as batch:
        for col in (
            "click_count",
            "link_clicked_at",
            "open_count",
            "opened_at",
            "email_sent_at",
            "tracking_token",
        ):
            if _has_column("demo_requests", col):
                batch.drop_column(col)
