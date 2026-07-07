"""0155 — custom_org_profiles table (WA Profiles / per-customer workspace)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0155_custom_org_profiles"
down_revision = "0154_feedback_session_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_org_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("internal_ref", sa.String(length=32), nullable=True),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("wa_profile_id", sa.String(length=36), nullable=True),
        sa.Column("calling_profile_id", sa.String(length=36), nullable=True),
        sa.Column("plan_id", sa.String(length=36), nullable=True),
        sa.Column("contact_name", sa.String(length=128), nullable=True),
        sa.Column("contact_email", sa.String(length=190), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="setup"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["wa_profile_id"], ["connection_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["calling_profile_id"], ["connection_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_custom_org_profiles_internal_ref", "custom_org_profiles", ["internal_ref"])
    op.create_index("ix_custom_org_profiles_org_id", "custom_org_profiles", ["org_id"])
    op.create_index("ix_custom_org_profiles_status", "custom_org_profiles", ["status"])


def downgrade() -> None:
    op.drop_index("ix_custom_org_profiles_status", table_name="custom_org_profiles")
    op.drop_index("ix_custom_org_profiles_org_id", table_name="custom_org_profiles")
    op.drop_index("ix_custom_org_profiles_internal_ref", table_name="custom_org_profiles")
    op.drop_table("custom_org_profiles")
