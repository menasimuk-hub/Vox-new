"""0158 — custom org phase 3: template org ownership + profile service flags."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0158_custom_org_phase3"
down_revision = "0157_wa_template_profile_status"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_column(bind, "telnyx_whatsapp_templates", "org_id"):
        op.add_column(
            "telnyx_whatsapp_templates",
            sa.Column("org_id", sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            "fk_telnyx_wa_tpl_org",
            "telnyx_whatsapp_templates",
            "organisations",
            ["org_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_telnyx_wa_tpl_org_id", "telnyx_whatsapp_templates", ["org_id"])

    if not _has_column(bind, "custom_org_profiles", "survey_enabled"):
        op.add_column(
            "custom_org_profiles",
            sa.Column("survey_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if not _has_column(bind, "custom_org_profiles", "feedback_enabled"):
        op.add_column(
            "custom_org_profiles",
            sa.Column("feedback_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "custom_org_profiles", "feedback_enabled"):
        op.drop_column("custom_org_profiles", "feedback_enabled")
    if _has_column(bind, "custom_org_profiles", "survey_enabled"):
        op.drop_column("custom_org_profiles", "survey_enabled")
    if _has_column(bind, "telnyx_whatsapp_templates", "org_id"):
        op.drop_index("ix_telnyx_wa_tpl_org_id", table_name="telnyx_whatsapp_templates")
        op.drop_constraint("fk_telnyx_wa_tpl_org", "telnyx_whatsapp_templates", type_="foreignkey")
        op.drop_column("telnyx_whatsapp_templates", "org_id")
