"""0159 — custom org profiles: separate Customer Feedback billing plan."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0159_custom_org_feedback_plan"
down_revision = "0158_custom_org_phase3"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "custom_org_profiles", "feedback_plan_id"):
        op.add_column(
            "custom_org_profiles",
            sa.Column("feedback_plan_id", sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            "fk_custom_org_profiles_feedback_plan",
            "custom_org_profiles",
            "plans",
            ["feedback_plan_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_custom_org_profiles_feedback_plan_id",
            "custom_org_profiles",
            ["feedback_plan_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "custom_org_profiles", "feedback_plan_id"):
        op.drop_index("ix_custom_org_profiles_feedback_plan_id", table_name="custom_org_profiles")
        op.drop_constraint("fk_custom_org_profiles_feedback_plan", "custom_org_profiles", type_="foreignkey")
        op.drop_column("custom_org_profiles", "feedback_plan_id")
