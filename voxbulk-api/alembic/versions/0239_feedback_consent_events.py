"""Add feedback_consent_events ledger table.

MySQL note: FK to organisations.id must match that column's charset/collation
(error 3780 otherwise). We omit DB foreign keys (indexes only) — same approach as
0235_smart_card_engagement_events — so deploy succeeds on mixed-collation VPS DBs.
Idempotent for partial failed runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0239_feedback_consent_events"
down_revision = "0238_feedback_callback_consent"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in sa.inspect(bind).get_table_names()


def _has_index(table: str, name: str) -> bool:
    bind = op.get_bind()
    if not _has_table(table):
        return False
    return any(ix["name"] == name for ix in sa.inspect(bind).get_indexes(table))


def _column_collation(table: str, column: str) -> str | None:
    bind = op.get_bind()
    try:
        return bind.execute(
            sa.text(
                "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = :table AND COLUMN_NAME = :column "
                "LIMIT 1"
            ),
            {"table": table, "column": column},
        ).scalar()
    except Exception:
        return None


def _id_type(collation: str | None) -> sa.String:
    return sa.String(36, collation=collation) if collation else sa.String(36)


def _str_type(length: int, collation: str | None) -> sa.String:
    return sa.String(length, collation=collation) if collation else sa.String(length)


def _table_kwargs(collation: str | None) -> dict:
    if not collation:
        return {}
    return {"mysql_charset": "utf8mb4", "mysql_collate": collation}


def upgrade() -> None:
    if _has_table("feedback_consent_events"):
        return

    org_collation = _column_collation("organisations", "id")

    # No ForeignKeyConstraint — avoids MySQL errno 3780 charset/collation FK failures on VPS.
    op.create_table(
        "feedback_consent_events",
        sa.Column("id", _id_type(org_collation), nullable=False),
        sa.Column("org_id", _id_type(org_collation), nullable=False),
        sa.Column("session_id", _id_type(org_collation), nullable=True),
        sa.Column("location_id", _id_type(org_collation), nullable=True),
        sa.Column("purpose", _str_type(32, org_collation), nullable=False),
        sa.Column("consent_given", sa.Boolean(), nullable=False),
        sa.Column("phone_e164", _str_type(32, org_collation), nullable=False),
        sa.Column("question_text_snapshot", sa.Text(), nullable=True),
        sa.Column("question_version_id", _str_type(64, org_collation), nullable=True),
        sa.Column("method", _str_type(32, org_collation), nullable=False),
        sa.Column("source_event", _str_type(16, org_collation), nullable=False),
        sa.Column("ip_address", _str_type(64, org_collation), nullable=True),
        sa.Column("user_agent", _str_type(512, org_collation), nullable=True),
        sa.Column("created_by_user_id", _id_type(org_collation), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        **_table_kwargs(org_collation),
    )

    for ix_name, cols in (
        ("ix_feedback_consent_events_org_id", ["org_id"]),
        ("ix_feedback_consent_events_session_id", ["session_id"]),
        ("ix_feedback_consent_events_location_id", ["location_id"]),
        ("ix_feedback_consent_events_purpose", ["purpose"]),
        ("ix_feedback_consent_events_phone_e164", ["phone_e164"]),
        ("ix_feedback_consent_events_created_at", ["created_at"]),
    ):
        if not _has_index("feedback_consent_events", ix_name):
            op.create_index(ix_name, "feedback_consent_events", cols)


def downgrade() -> None:
    if not _has_table("feedback_consent_events"):
        return
    for ix_name in (
        "ix_feedback_consent_events_created_at",
        "ix_feedback_consent_events_phone_e164",
        "ix_feedback_consent_events_purpose",
        "ix_feedback_consent_events_location_id",
        "ix_feedback_consent_events_session_id",
        "ix_feedback_consent_events_org_id",
    ):
        if _has_index("feedback_consent_events", ix_name):
            op.drop_index(ix_name, table_name="feedback_consent_events")
    op.drop_table("feedback_consent_events")
