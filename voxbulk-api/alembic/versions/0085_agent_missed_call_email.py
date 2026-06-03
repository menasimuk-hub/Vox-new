"""Agent missed-call follow-up email settings per service."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0085_agent_missed_call_email"
down_revision = "0084_ai_team_email_template"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has_column("agent_definitions", "missed_call_email_template_interview"):
        op.add_column(
            "agent_definitions",
            sa.Column("missed_call_email_template_interview", sa.String(64), nullable=True),
        )
    if not _has_column("agent_definitions", "missed_call_email_template_survey"):
        op.add_column(
            "agent_definitions",
            sa.Column("missed_call_email_template_survey", sa.String(64), nullable=True),
        )
    if not _has_column("agent_definitions", "missed_call_followup_notes_interview"):
        op.add_column(
            "agent_definitions",
            sa.Column("missed_call_followup_notes_interview", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("agent_definitions", "missed_call_followup_notes_interview"):
        op.drop_column("agent_definitions", "missed_call_followup_notes_interview")
    if _has_column("agent_definitions", "missed_call_email_template_survey"):
        op.drop_column("agent_definitions", "missed_call_email_template_survey")
    if _has_column("agent_definitions", "missed_call_email_template_interview"):
        op.drop_column("agent_definitions", "missed_call_email_template_interview")
