"""Drop legacy global unique on survey_types.slug (SQLite 0091 did not remove ix_survey_types_slug)."""

from alembic import op
import sqlalchemy as sa

revision = "0096_survey_types_slug_scope_fix"
down_revision = "0095_wa_survey_ai_picker_p4"
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


def _sqlite_index_exists(conn, table: str, index_name: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:t AND name=:n"
        ),
        {"t": table, "n": index_name},
    ).fetchone()
    return row is not None


def _constraint_exists_pg(conn, table: str, name: str) -> bool:
    row = conn.execute(
        sa.text(
            "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND CONSTRAINT_NAME = :n"
        ),
        {"t": table, "n": name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "survey_types"):
        return

    if conn.dialect.name == "sqlite":
        if _sqlite_index_exists(conn, "survey_types", "ix_survey_types_slug"):
            with op.batch_alter_table("survey_types") as batch_op:
                batch_op.drop_index("ix_survey_types_slug")
        with op.batch_alter_table("survey_types") as batch_op:
            try:
                batch_op.create_unique_constraint(
                    "uq_survey_types_industry_slug", ["industry_id", "slug"]
                )
            except Exception:
                pass
        return

    try:
        op.drop_constraint("survey_types_slug_key", "survey_types", type_="unique")
    except Exception:
        try:
            op.drop_index("ix_survey_types_slug", table_name="survey_types")
        except Exception:
            pass
    if not _constraint_exists_pg(conn, "survey_types", "uq_survey_types_industry_slug"):
        op.create_unique_constraint(
            "uq_survey_types_industry_slug", "survey_types", ["industry_id", "slug"]
        )


def downgrade() -> None:
    pass
