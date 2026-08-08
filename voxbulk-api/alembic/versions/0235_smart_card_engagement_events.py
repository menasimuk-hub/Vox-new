"""Add smart_card_engagement_events for public card click KPIs.

MySQL note: FK to organisations.id must match that column's charset/collation
(error 3780 otherwise). We omit DB foreign keys (indexes only) — same approach as
smart_card_voice_note_jobs — so deploy succeeds on mixed-collation VPS DBs.
Idempotent for partial failed runs.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0235_smart_card_engagement_events"
down_revision = "0234_qr_style_options"
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


def _table_kwargs(collation: str | None) -> dict:
    if not collation:
        return {}
    return {"mysql_charset": "utf8mb4", "mysql_collate": collation}


def upgrade() -> None:
    if _has_table("smart_card_engagement_events"):
        return

    org_collation = _column_collation("organisations", "id")
    rep_collation = _column_collation("smart_card_representatives", "id") or org_collation

    # No ForeignKeyConstraint — avoids MySQL errno 3780 charset/collation FK failures on VPS.
    op.create_table(
        "smart_card_engagement_events",
        sa.Column("id", _id_type(org_collation), nullable=False),
        sa.Column("org_id", _id_type(org_collation), nullable=False),
        sa.Column("representative_id", _id_type(rep_collation), nullable=False),
        sa.Column("lead_id", _id_type(org_collation), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        **_table_kwargs(org_collation),
    )

    for ix_name, cols in (
        ("ix_sc_eng_events_org_id", ["org_id"]),
        ("ix_sc_eng_events_rep_id", ["representative_id"]),
        ("ix_sc_eng_events_lead_id", ["lead_id"]),
        ("ix_sc_eng_events_type", ["event_type"]),
        ("ix_sc_eng_events_created", ["created_at"]),
        ("ix_sc_eng_events_org_rep_type_created", ["org_id", "representative_id", "event_type", "created_at"]),
    ):
        if not _has_index("smart_card_engagement_events", ix_name):
            op.create_index(ix_name, "smart_card_engagement_events", cols)


def downgrade() -> None:
    if not _has_table("smart_card_engagement_events"):
        return
    for ix_name in (
        "ix_sc_eng_events_org_rep_type_created",
        "ix_sc_eng_events_created",
        "ix_sc_eng_events_type",
        "ix_sc_eng_events_lead_id",
        "ix_sc_eng_events_rep_id",
        "ix_sc_eng_events_org_id",
    ):
        if _has_index("smart_card_engagement_events", ix_name):
            op.drop_index(ix_name, table_name="smart_card_engagement_events")
    op.drop_table("smart_card_engagement_events")
