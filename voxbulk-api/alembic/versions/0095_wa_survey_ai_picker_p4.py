"""P4: WA Survey AI picker platform settings and session invocation counter."""

from alembic import op
import sqlalchemy as sa

revision = "0095_wa_survey_ai_picker_p4"
down_revision = "0094_wa_survey_outcome_templates_p3"
branch_labels = None
depends_on = None


def _table_exists(conn, name: str) -> bool:
    if conn.dialect.name == "sqlite":
        return (
            conn.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
                {"n": name},
            ).fetchone()
            is not None
        )
    return (
        conn.execute(
            sa.text(
                "SELECT TABLE_NAME FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :n"
            ),
            {"n": name},
        ).fetchone()
        is not None
    )


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
    if not _table_exists(conn, "wa_survey_platform_settings"):
        op.create_table(
            "wa_survey_platform_settings",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("ai_picker_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        from datetime import datetime

        op.bulk_insert(
            sa.table(
                "wa_survey_platform_settings",
                sa.column("id", sa.String),
                sa.column("ai_picker_enabled", sa.Boolean),
                sa.column("updated_at", sa.DateTime),
            ),
            [{"id": "default", "ai_picker_enabled": True, "updated_at": datetime.utcnow()}],
        )

    if _table_exists(conn, "survey_sessions"):
        if not _column_exists(conn, "survey_sessions", "picker_invocation_count"):
            op.add_column(
                "survey_sessions",
                sa.Column("picker_invocation_count", sa.Integer(), nullable=False, server_default="0"),
            )


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "survey_sessions") and _column_exists(conn, "survey_sessions", "picker_invocation_count"):
        op.drop_column("survey_sessions", "picker_invocation_count")
    if _table_exists(conn, "wa_survey_platform_settings"):
        op.drop_table("wa_survey_platform_settings")
