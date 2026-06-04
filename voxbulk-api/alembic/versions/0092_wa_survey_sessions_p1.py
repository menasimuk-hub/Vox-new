"""P1: survey_sessions, survey_session_answers, survey_session_decisions."""

from alembic import op
import sqlalchemy as sa

revision = "0092_wa_survey_sessions_p1"
down_revision = "0091_wa_survey_industries"
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


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "survey_sessions"):
        op.create_table(
            "survey_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("order_id", sa.String(36), sa.ForeignKey("service_orders.id"), nullable=False),
            sa.Column(
                "recipient_id",
                sa.String(36),
                sa.ForeignKey("service_order_recipients.id"),
                nullable=False,
            ),
            sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("channel", sa.String(32), nullable=False, server_default="whatsapp"),
            sa.Column("status", sa.String(32), nullable=False, server_default="active"),
            sa.Column("flow_mode", sa.String(32), nullable=False, server_default="linear"),
            sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("total_steps", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("page_roles_json", sa.Text(), nullable=True),
            sa.Column("survey_type_id", sa.String(36), sa.ForeignKey("survey_types.id"), nullable=True),
            sa.Column("privacy_mode", sa.String(32), nullable=True),
            sa.Column("outcome_key", sa.String(64), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("recipient_id", name="uq_survey_sessions_recipient"),
        )
        op.create_index("ix_survey_sessions_order_id", "survey_sessions", ["order_id"])
        op.create_index("ix_survey_sessions_org_id", "survey_sessions", ["org_id"])
        op.create_index("ix_survey_sessions_status", "survey_sessions", ["status"])

    if not _table_exists(conn, "survey_session_answers"):
        op.create_table(
            "survey_session_answers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "session_id",
                sa.String(36),
                sa.ForeignKey("survey_sessions.id"),
                nullable=False,
            ),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("step_index", sa.Integer(), nullable=False),
            sa.Column("step_role", sa.String(32), nullable=False),
            sa.Column("node_key", sa.String(64), nullable=False),
            sa.Column("question_text", sa.Text(), nullable=True),
            sa.Column("raw_value", sa.Text(), nullable=True),
            sa.Column("normalized_value", sa.Text(), nullable=True),
            sa.Column("reply_type", sa.String(32), nullable=True),
            sa.Column("template_id", sa.Integer(), nullable=True),
            sa.Column("answered_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("session_id", "sequence", name="uq_survey_session_answers_seq"),
        )
        op.create_index("ix_survey_session_answers_session_id", "survey_session_answers", ["session_id"])
        op.create_index("ix_survey_session_answers_step_role", "survey_session_answers", ["step_role"])

    if not _table_exists(conn, "survey_session_decisions"):
        op.create_table(
            "survey_session_decisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "session_id",
                sa.String(36),
                sa.ForeignKey("survey_sessions.id"),
                nullable=False,
            ),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("decision_kind", sa.String(64), nullable=False),
            sa.Column("rule_key", sa.String(64), nullable=False),
            sa.Column("picker", sa.String(32), nullable=False, server_default="deterministic"),
            sa.Column("from_step", sa.Integer(), nullable=True),
            sa.Column("to_step", sa.Integer(), nullable=True),
            sa.Column("from_role", sa.String(32), nullable=True),
            sa.Column("to_role", sa.String(32), nullable=True),
            sa.Column("reason", sa.String(255), nullable=True),
            sa.Column("context_json", sa.Text(), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("session_id", "sequence", name="uq_survey_session_decisions_seq"),
        )
        op.create_index("ix_survey_session_decisions_session_id", "survey_session_decisions", ["session_id"])
        op.create_index(
            "ix_survey_session_decisions_decision_kind",
            "survey_session_decisions",
            ["decision_kind"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _table_exists(conn, "survey_session_decisions"):
        op.drop_table("survey_session_decisions")
    if _table_exists(conn, "survey_session_answers"):
        op.drop_table("survey_session_answers")
    if _table_exists(conn, "survey_sessions"):
        op.drop_table("survey_sessions")
