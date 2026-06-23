"""Customer feedback survey types: admin WA marketing block override."""

from alembic import op
import sqlalchemy as sa

revision = "0132_feedback_survey_type_wa_block_exempt"
down_revision = "0131_appointment_calendar_post_survey"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("feedback_survey_types", "wa_platform_block_exempt"):
        op.add_column(
            "feedback_survey_types",
            sa.Column("wa_platform_block_exempt", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    if _column_exists("feedback_survey_types", "wa_platform_block_exempt"):
        op.drop_column("feedback_survey_types", "wa_platform_block_exempt")
