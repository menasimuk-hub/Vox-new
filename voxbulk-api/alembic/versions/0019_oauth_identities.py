"""oauth identities (social login linking)

Revision ID: 0019_oauth_identities
Revises: 0018_categories_and_org_profile_fields
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_oauth_identities"
down_revision = "0018_categories_and_org_profile_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_oauth_identities_provider", "oauth_identities", ["provider"], unique=False)
    op.create_index("ix_oauth_identities_provider_user_id", "oauth_identities", ["provider_user_id"], unique=False)
    op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"], unique=False)
    op.create_unique_constraint(
        "uq_oauth_identities_provider_user",
        "oauth_identities",
        ["provider", "provider_user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_oauth_identities_provider_user", "oauth_identities", type_="unique")
    op.drop_index("ix_oauth_identities_user_id", table_name="oauth_identities")
    op.drop_index("ix_oauth_identities_provider_user_id", table_name="oauth_identities")
    op.drop_index("ix_oauth_identities_provider", table_name="oauth_identities")
    op.drop_table("oauth_identities")

