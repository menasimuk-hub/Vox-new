"""0253 — Track when staff open a feedback session in results.

Revision ID: 0253_feedback_session_dashboard_opened
Revises: 0252_user_preferred_org
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0253_feedback_session_dashboard_opened"
down_revision = "0252_user_preferred_org"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedback_sessions",
        sa.Column("dashboard_opened_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_feedback_sessions_dashboard_opened_at",
        "feedback_sessions",
        ["dashboard_opened_at"],
        unique=False,
    )
    # Existing responses are historical — treat as already opened so only new replies show as New.
    op.execute(
        """
        UPDATE feedback_sessions
        SET dashboard_opened_at = COALESCE(completed_at, started_at, created_at)
        WHERE dashboard_opened_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_sessions_dashboard_opened_at", table_name="feedback_sessions")
    op.drop_column("feedback_sessions", "dashboard_opened_at")
