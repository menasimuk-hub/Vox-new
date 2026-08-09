"""Add feedback_consent_events ledger table.

Idempotent create for MySQL/SQLite.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0239_feedback_consent_events"
down_revision = "0238_feedback_callback_consent"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    if _has_table("feedback_consent_events"):
        return
    op.create_table(
        "feedback_consent_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("feedback_sessions.id"), nullable=True),
        sa.Column("location_id", sa.String(length=36), sa.ForeignKey("feedback_locations.id"), nullable=True),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("consent_given", sa.Boolean(), nullable=False),
        sa.Column("phone_e164", sa.String(length=32), nullable=False),
        sa.Column("question_text_snapshot", sa.Text(), nullable=True),
        sa.Column("question_version_id", sa.String(length=64), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("source_event", sa.String(length=16), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_feedback_consent_events_org_id", "feedback_consent_events", ["org_id"])
    op.create_index("ix_feedback_consent_events_session_id", "feedback_consent_events", ["session_id"])
    op.create_index("ix_feedback_consent_events_location_id", "feedback_consent_events", ["location_id"])
    op.create_index("ix_feedback_consent_events_purpose", "feedback_consent_events", ["purpose"])
    op.create_index("ix_feedback_consent_events_phone_e164", "feedback_consent_events", ["phone_e164"])
    op.create_index("ix_feedback_consent_events_created_at", "feedback_consent_events", ["created_at"])


def downgrade() -> None:
    if _has_table("feedback_consent_events"):
        op.drop_table("feedback_consent_events")
