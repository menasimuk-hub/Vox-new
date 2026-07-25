"""Private org packages: is_private plans + multi-org assignment + unit rates.

Revision ID: 0184_private_org_packages
Revises: 0183_expo_card_voice
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0184_private_org_packages"
down_revision = "0183_expo_card_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.create_table(
        "org_package_assignments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("service_kind", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_id", "service_kind", name="uq_org_package_assignment_org_service"),
    )
    op.create_index("ix_org_package_assignments_org_id", "org_package_assignments", ["org_id"])
    op.create_index("ix_org_package_assignments_plan_id", "org_package_assignments", ["plan_id"])
    op.create_index("ix_org_package_assignments_service_kind", "org_package_assignments", ["service_kind"])

    op.create_table(
        "plan_unit_rates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("connection_fee_minor", sa.Integer(), nullable=True),
        sa.Column("interview_per_min_minor", sa.Integer(), nullable=True),
        sa.Column("wa_package_fee_minor", sa.Integer(), nullable=True),
        sa.Column("wa_extra_minor", sa.Integer(), nullable=True),
        sa.Column("cv_scan_fee_minor", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("plan_id", "currency", name="uq_plan_unit_rate_plan_currency"),
    )
    op.create_index("ix_plan_unit_rates_plan_id", "plan_unit_rates", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_plan_unit_rates_plan_id", table_name="plan_unit_rates")
    op.drop_table("plan_unit_rates")
    op.drop_index("ix_org_package_assignments_service_kind", table_name="org_package_assignments")
    op.drop_index("ix_org_package_assignments_plan_id", table_name="org_package_assignments")
    op.drop_index("ix_org_package_assignments_org_id", table_name="org_package_assignments")
    op.drop_table("org_package_assignments")
    op.drop_column("plans", "is_private")
