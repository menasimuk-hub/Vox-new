"""0157 — wa_template_profile_status (per-connection-profile approval registry)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0157_wa_template_profile_status"
down_revision = "0156_feedback_meta_template_name"
branch_labels = None
depends_on = None

_TABLE = "wa_template_profile_status"


def _has_table(bind) -> bool:
    return sa.inspect(bind).has_table(_TABLE)


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("profile_key", sa.String(length=64), nullable=False),
        sa.Column("connection_profile_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=16), nullable=True),
        sa.Column("profile_label", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="UNKNOWN"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("remote_record_id", sa.String(length=64), nullable=True),
        sa.Column("remote_template_id", sa.String(length=64), nullable=True),
        sa.Column("waba_id", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("last_pushed_at", sa.DateTime(), nullable=True),
        sa.Column("last_push_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["template_id"], ["telnyx_whatsapp_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_profile_id"], ["connection_profiles.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("template_id", "profile_key", name="uq_wa_tpl_profile_status"),
    )
    op.create_index("ix_wa_template_profile_status_template_id", _TABLE, ["template_id"])
    op.create_index("ix_wa_template_profile_status_profile_key", _TABLE, ["profile_key"])
    op.create_index(
        "ix_wa_template_profile_status_connection_profile_id", _TABLE, ["connection_profile_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind):
        return
    op.drop_index("ix_wa_template_profile_status_connection_profile_id", table_name=_TABLE)
    op.drop_index("ix_wa_template_profile_status_profile_key", table_name=_TABLE)
    op.drop_index("ix_wa_template_profile_status_template_id", table_name=_TABLE)
    op.drop_table(_TABLE)
