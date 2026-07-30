"""0214 — Smart Card mailbox IMAP/SMTP, industries, voice note jobs.

Revision ID: 0214_smart_card_mailbox_imap
Revises: 0213_smart_card_qr_foundation

Idempotent for MySQL non-transactional DDL (safe to re-run after a partial failure).
Voice note jobs omit DB foreign keys — MySQL charset/engine mismatches on FK create
were failing deploy; app integrity is enough for job rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0214_smart_card_mailbox_imap"
down_revision = "0213_smart_card_qr_foundation"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    return any(ix["name"] == index_name for ix in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    if _has_table("smart_card_mailbox_settings"):
        cols = [
            ("smtp_host", sa.Column("smtp_host", sa.String(length=255), nullable=True)),
            ("smtp_port", sa.Column("smtp_port", sa.Integer(), nullable=True)),
            ("imap_host", sa.Column("imap_host", sa.String(length=255), nullable=True)),
            ("imap_port", sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993")),
            (
                "imap_use_ssl",
                sa.Column("imap_use_ssl", sa.Boolean(), nullable=False, server_default=sa.true()),
            ),
            (
                "imap_use_tls",
                sa.Column("imap_use_tls", sa.Boolean(), nullable=False, server_default=sa.false()),
            ),
            ("imap_username", sa.Column("imap_username", sa.String(length=255), nullable=True)),
            ("imap_password_encrypted", sa.Column("imap_password_encrypted", sa.Text(), nullable=True)),
            ("imap_last_sync_at", sa.Column("imap_last_sync_at", sa.DateTime(), nullable=True)),
            (
                "imap_last_sync_message",
                sa.Column("imap_last_sync_message", sa.String(length=512), nullable=True),
            ),
        ]
        for name, col in cols:
            if not _has_column("smart_card_mailbox_settings", name):
                op.add_column("smart_card_mailbox_settings", col)

    if not _has_table("smart_card_industries"):
        op.create_table(
            "smart_card_industries",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("addon_question", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_table("smart_card_voice_note_jobs"):
        # No ForeignKeyConstraint — avoids MySQL errno 150 charset/engine FK failures on VPS.
        op.create_table(
            "smart_card_voice_note_jobs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("org_id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("storage_path", sa.Text(), nullable=True),
            sa.Column("transcript", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if _has_table("smart_card_voice_note_jobs"):
        for ix_name, cols in (
            ("ix_smart_card_voice_note_jobs_org_id", ["org_id"]),
            ("ix_smart_card_voice_note_jobs_session_id", ["session_id"]),
            ("ix_smart_card_voice_note_jobs_status", ["status"]),
        ):
            if not _has_index("smart_card_voice_note_jobs", ix_name):
                op.create_index(ix_name, "smart_card_voice_note_jobs", cols)


def downgrade() -> None:
    if _has_table("smart_card_voice_note_jobs"):
        for ix_name in (
            "ix_smart_card_voice_note_jobs_status",
            "ix_smart_card_voice_note_jobs_session_id",
            "ix_smart_card_voice_note_jobs_org_id",
        ):
            if _has_index("smart_card_voice_note_jobs", ix_name):
                op.drop_index(ix_name, table_name="smart_card_voice_note_jobs")
        op.drop_table("smart_card_voice_note_jobs")
    if _has_table("smart_card_industries"):
        op.drop_table("smart_card_industries")
    if _has_table("smart_card_mailbox_settings"):
        for col in (
            "imap_last_sync_message",
            "imap_last_sync_at",
            "imap_password_encrypted",
            "imap_username",
            "imap_use_tls",
            "imap_use_ssl",
            "imap_port",
            "imap_host",
            "smtp_port",
            "smtp_host",
        ):
            if _has_column("smart_card_mailbox_settings", col):
                op.drop_column("smart_card_mailbox_settings", col)
