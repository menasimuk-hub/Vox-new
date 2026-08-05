"""Smart Card representative profile photo path."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0227_smart_card_rep_photo"
down_revision = "0226_smart_card_response_voice_fields"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    table = "smart_card_representatives"
    if not _has_column(table, "photo_storage_path"):
        op.add_column(table, sa.Column("photo_storage_path", sa.Text(), nullable=True))


def downgrade() -> None:
    table = "smart_card_representatives"
    if _has_column(table, "photo_storage_path"):
        op.drop_column(table, "photo_storage_path")
