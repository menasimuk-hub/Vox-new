"""P2: survey flow definitions (nodes, edges, outcomes) and session graph fields."""

from alembic import op
import sqlalchemy as sa

revision = "0093_wa_survey_flow_graph_p2"
down_revision = "0092_wa_survey_sessions_p1"
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
    if not _table_exists(conn, "survey_flow_definitions"):
        op.create_table(
            "survey_flow_definitions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("survey_type_id", sa.String(36), sa.ForeignKey("survey_types.id"), nullable=False),
            sa.Column("privacy_mode", sa.String(8), nullable=False, server_default="off"),
            sa.Column("slug", sa.String(64), nullable=False, server_default="default"),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("entry_node_key", sa.String(64), nullable=False),
            sa.Column("fallback_outcome_key", sa.String(64), nullable=False, server_default="neutral"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "survey_type_id",
                "privacy_mode",
                "slug",
                "version",
                name="uq_survey_flow_def_type_privacy_slug_ver",
            ),
        )
        op.create_index("ix_survey_flow_definitions_survey_type_id", "survey_flow_definitions", ["survey_type_id"])
        op.create_index("ix_survey_flow_definitions_status", "survey_flow_definitions", ["status"])

    if not _table_exists(conn, "survey_flow_nodes"):
        op.create_table(
            "survey_flow_nodes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "flow_id",
                sa.String(36),
                sa.ForeignKey("survey_flow_definitions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("node_key", sa.String(64), nullable=False),
            sa.Column("node_type", sa.String(16), nullable=False),
            sa.Column("step_role", sa.String(32), nullable=True),
            sa.Column("template_id", sa.Integer(), nullable=True),
            sa.Column("title", sa.String(255), nullable=True),
            sa.Column("is_terminal", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("outcome_key", sa.String(64), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("flow_id", "node_key", name="uq_survey_flow_nodes_flow_key"),
        )
        op.create_index("ix_survey_flow_nodes_flow_id", "survey_flow_nodes", ["flow_id"])

    if not _table_exists(conn, "survey_flow_edges"):
        op.create_table(
            "survey_flow_edges",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "flow_id",
                sa.String(36),
                sa.ForeignKey("survey_flow_definitions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("from_node_key", sa.String(64), nullable=False),
            sa.Column("to_node_key", sa.String(64), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("rule_key", sa.String(64), nullable=False),
            sa.Column("condition_json", sa.Text(), nullable=True),
            sa.Column("label", sa.String(128), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("flow_id", "from_node_key", "priority", name="uq_survey_flow_edges_from_prio"),
        )
        op.create_index("ix_survey_flow_edges_flow_id", "survey_flow_edges", ["flow_id"])

    if not _table_exists(conn, "survey_flow_outcomes"):
        op.create_table(
            "survey_flow_outcomes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "flow_id",
                sa.String(36),
                sa.ForeignKey("survey_flow_definitions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("outcome_key", sa.String(64), nullable=False),
            sa.Column("node_key", sa.String(64), nullable=False),
            sa.Column("action_type", sa.String(32), nullable=False, server_default="send_text"),
            sa.Column("template_id", sa.Integer(), nullable=True),
            sa.Column("message_body", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("flow_id", "outcome_key", name="uq_survey_flow_outcomes_flow_key"),
            sa.UniqueConstraint("flow_id", "node_key", name="uq_survey_flow_outcomes_flow_node"),
        )
        op.create_index("ix_survey_flow_outcomes_flow_id", "survey_flow_outcomes", ["flow_id"])

    if _table_exists(conn, "survey_sessions"):
        for col, col_type in [
            ("flow_definition_id", sa.String(36)),
            ("flow_snapshot_json", sa.Text()),
            ("current_node_key", sa.String(64)),
            ("question_visits", sa.Integer()),
        ]:
            if not _column_exists(conn, "survey_sessions", col):
                kwargs: dict = {"nullable": True}
                if col == "question_visits":
                    kwargs = {"nullable": False, "server_default": "0"}
                op.add_column("survey_sessions", sa.Column(col, col_type, **kwargs))
        if not _column_exists(conn, "survey_sessions", "flow_definition_id"):
            pass
        else:
            try:
                op.create_foreign_key(
                    "fk_survey_sessions_flow_definition",
                    "survey_sessions",
                    "survey_flow_definitions",
                    ["flow_definition_id"],
                    ["id"],
                )
            except Exception:
                pass
        try:
            op.create_index("ix_survey_sessions_current_node_key", "survey_sessions", ["current_node_key"])
        except Exception:
            pass


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "survey_sessions"):
        for col in ("current_node_key", "flow_snapshot_json", "flow_definition_id", "question_visits"):
            if _column_exists(conn, "survey_sessions", col):
                try:
                    op.drop_column("survey_sessions", col)
                except Exception:
                    pass
    for table in ("survey_flow_outcomes", "survey_flow_edges", "survey_flow_nodes", "survey_flow_definitions"):
        if _table_exists(conn, table):
            op.drop_table(table)
