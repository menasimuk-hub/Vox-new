"""Disabled WA templates — store resolved survey type id so topics hide from the user dashboard."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0141_disabled_wa_template_survey_type"
down_revision = "0140_disabled_wa_templates"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        return any(col["name"] == column for col in inspector.get_columns(table))
    except Exception:
        return False


def upgrade() -> None:
    if not _has_column("disabled_wa_templates", "survey_type_id"):
        op.add_column("disabled_wa_templates", sa.Column("survey_type_id", sa.String(36), nullable=True))
    if not _has_column("disabled_wa_templates", "survey_type_kind"):
        op.add_column("disabled_wa_templates", sa.Column("survey_type_kind", sa.String(16), nullable=True))


def downgrade() -> None:
    if _has_column("disabled_wa_templates", "survey_type_kind"):
        op.drop_column("disabled_wa_templates", "survey_type_kind")
    if _has_column("disabled_wa_templates", "survey_type_id"):
        op.drop_column("disabled_wa_templates", "survey_type_id")
