"""0154 — feedback session JSON state for tell-us-more pending/timeouts."""

from alembic import op
import sqlalchemy as sa

revision = "0154_feedback_session_state"
down_revision = "0153_connection_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedback_sessions",
        sa.Column("session_state_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("feedback_sessions", "session_state_json")
