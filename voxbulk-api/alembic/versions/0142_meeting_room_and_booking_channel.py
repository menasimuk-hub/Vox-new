"""Meeting room platform settings + interview booking channel."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0142_meeting_room_and_booking_channel"
down_revision = "0141_disabled_wa_template_survey_type"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        return name in inspector.get_table_names()
    except Exception:
        return False


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        return any(col["name"] == column for col in inspector.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    if not _has_table("meeting_room_platform_settings"):
        op.create_table(
            "meeting_room_platform_settings",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("agent_id", sa.String(36), sa.ForeignKey("agent_definitions.id"), nullable=True),
            sa.Column("language_code", sa.String(16), nullable=False, server_default="en"),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        now = datetime.utcnow()
        op.bulk_insert(
            sa.table(
                "meeting_room_platform_settings",
                sa.column("id", sa.String),
                sa.column("agent_id", sa.String),
                sa.column("language_code", sa.String),
                sa.column("updated_at", sa.DateTime),
            ),
            [
                {
                    "id": "default",
                    "agent_id": None,
                    "language_code": "en",
                    "updated_at": now,
                }
            ],
        )

    if not _has_column("interview_booking_tokens", "channel"):
        op.add_column(
            "interview_booking_tokens",
            sa.Column("channel", sa.String(16), nullable=True),
        )


def downgrade() -> None:
    if _has_column("interview_booking_tokens", "channel"):
        op.drop_column("interview_booking_tokens", "channel")
    if _has_table("meeting_room_platform_settings"):
        op.drop_table("meeting_room_platform_settings")
