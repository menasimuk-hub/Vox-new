"""Hidden system industry, survey type roles, industry is_hidden flag."""

from alembic import op
import sqlalchemy as sa

revision = "0098_survey_system_templates"
down_revision = "0097_uk_compliance_baseline"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    if conn.dialect.name == "sqlite":
        rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
        return any(str(r[1]) == column for r in rows)
    return (
        conn.execute(
            sa.text(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
            ),
            {"t": table, "c": column},
        ).fetchone()
        is not None
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "industries", "is_hidden"):
        op.add_column(
            "industries",
            sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not _column_exists(conn, "survey_types", "system_template_kind"):
        op.add_column(
            "survey_types",
            sa.Column("system_template_kind", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "survey_types", "system_template_kind"):
        op.drop_column("survey_types", "system_template_kind")
    if _column_exists(conn, "industries", "is_hidden"):
        op.drop_column("industries", "is_hidden")
