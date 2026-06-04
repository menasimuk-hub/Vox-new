"""P3: outcome_key on completion templates and session outcome delivery log."""

from alembic import op
import sqlalchemy as sa

revision = "0094_wa_survey_outcome_templates_p3"
down_revision = "0093_wa_survey_flow_graph_p2"
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
    if _table_exists(conn, "telnyx_whatsapp_templates"):
        if not _column_exists(conn, "telnyx_whatsapp_templates", "outcome_key"):
            op.add_column("telnyx_whatsapp_templates", sa.Column("outcome_key", sa.String(16), nullable=True))
            op.create_index("ix_telnyx_wa_tpl_outcome_key", "telnyx_whatsapp_templates", ["outcome_key"])
        if not _column_exists(conn, "telnyx_whatsapp_templates", "outcome_variables_json"):
            op.add_column("telnyx_whatsapp_templates", sa.Column("outcome_variables_json", sa.Text(), nullable=True))

    if _table_exists(conn, "survey_sessions"):
        if not _column_exists(conn, "survey_sessions", "outcome_delivery_json"):
            op.add_column("survey_sessions", sa.Column("outcome_delivery_json", sa.Text(), nullable=True))

    if _table_exists(conn, "survey_flow_outcomes"):
        try:
            op.create_foreign_key(
                "fk_survey_flow_outcomes_template",
                "survey_flow_outcomes",
                "telnyx_whatsapp_templates",
                ["template_id"],
                ["id"],
            )
        except Exception:
            pass


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "survey_flow_outcomes"):
        try:
            op.drop_constraint("fk_survey_flow_outcomes_template", "survey_flow_outcomes", type_="foreignkey")
        except Exception:
            pass
    if _table_exists(conn, "survey_sessions") and _column_exists(conn, "survey_sessions", "outcome_delivery_json"):
        op.drop_column("survey_sessions", "outcome_delivery_json")
    if _table_exists(conn, "telnyx_whatsapp_templates"):
        for col in ("outcome_variables_json", "outcome_key"):
            if _column_exists(conn, "telnyx_whatsapp_templates", col):
                op.drop_column("telnyx_whatsapp_templates", col)
