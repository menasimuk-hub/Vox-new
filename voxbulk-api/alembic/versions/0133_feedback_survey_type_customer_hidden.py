"""Customer feedback: explicit customer_hidden flag on survey types."""

from alembic import op
import sqlalchemy as sa

revision = "0133_feedback_survey_type_customer_hidden"
down_revision = "0132_feedback_survey_type_wa_block_exempt"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("feedback_survey_types", "customer_hidden"):
        op.add_column(
            "feedback_survey_types",
            sa.Column("customer_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    op.execute(
        sa.text(
            "UPDATE feedback_survey_types "
            "SET customer_hidden = CASE WHEN is_active = 0 OR is_active IS NULL THEN 1 ELSE 0 END"
        )
    )


def downgrade() -> None:
    if _column_exists("feedback_survey_types", "customer_hidden"):
        op.drop_column("feedback_survey_types", "customer_hidden")
