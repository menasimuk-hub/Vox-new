"""Appointment Manager: calendar event id + post-visit survey timestamp."""

from alembic import op
import sqlalchemy as sa

revision = "0131_appointment_calendar_post_survey"
down_revision = "0130_appointment_wa_templates"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("appointments", "calendar_event_id"):
        op.add_column("appointments", sa.Column("calendar_event_id", sa.String(255), nullable=True))
    if not _column_exists("appointments", "post_survey_sent_at"):
        op.add_column("appointments", sa.Column("post_survey_sent_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if _column_exists("appointments", "post_survey_sent_at"):
        op.drop_column("appointments", "post_survey_sent_at")
    if _column_exists("appointments", "calendar_event_id"):
        op.drop_column("appointments", "calendar_event_id")
