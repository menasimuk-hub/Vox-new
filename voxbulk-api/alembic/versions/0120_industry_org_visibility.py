"""Industry org visibility and duplicate lineage."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0120_industry_org_visibility"
down_revision = "0119_customer_feedback_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "industries",
        sa.Column("visibility_mode", sa.String(length=16), nullable=False, server_default="all"),
    )
    op.add_column(
        "industries",
        sa.Column("source_industry_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_industries_source_industry_id",
        "industries",
        "industries",
        ["source_industry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_industries_source_industry_id", "industries", ["source_industry_id"])

    op.create_table(
        "industry_organisations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("industry_id", sa.String(length=36), sa.ForeignKey("industries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("industry_id", "org_id", name="uq_industry_organisations_industry_org"),
    )
    op.create_index("ix_industry_organisations_org_id", "industry_organisations", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_industry_organisations_org_id", table_name="industry_organisations")
    op.drop_table("industry_organisations")
    op.drop_index("ix_industries_source_industry_id", table_name="industries")
    op.drop_constraint("fk_industries_source_industry_id", "industries", type_="foreignkey")
    op.drop_column("industries", "source_industry_id")
    op.drop_column("industries", "visibility_mode")
