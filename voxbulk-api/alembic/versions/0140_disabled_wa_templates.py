"""Disabled WA templates — admin list to hide costly/reclassified templates."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0140_disabled_wa_templates"
down_revision = "0139_feedback_sessions_visitor_phone_widen"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("disabled_wa_templates"):
        return
    op.create_table(
        "disabled_wa_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("normalized_name", sa.String(128), nullable=False, index=True),
        sa.Column("raw_name", sa.String(128), nullable=False),
        sa.Column("product_line", sa.String(64), nullable=False, server_default=""),
        sa.Column("industry_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("survey_type_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("target_kind", sa.String(16), nullable=False, server_default="unresolved"),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("prior_flags_json", sa.Text(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("normalized_name", name="uq_disabled_wa_tpl_normalized_name"),
    )


def downgrade() -> None:
    if _has_table("disabled_wa_templates"):
        op.drop_table("disabled_wa_templates")
