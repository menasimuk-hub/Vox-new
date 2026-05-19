"""categories + organisation profile fields

Revision ID: 0018_categories_and_org_profile_fields
Revises: 0017_organisation_invites
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_categories_and_org_profile_fields"
down_revision = "0017_organisation_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_unique_constraint("uq_categories_slug", "categories", ["slug"])
    op.create_index("ix_categories_slug", "categories", ["slug"], unique=False)

    op.add_column("organisations", sa.Column("category_id", sa.String(length=36), nullable=True))
    op.create_index("ix_organisations_category_id", "organisations", ["category_id"], unique=False)
    op.create_foreign_key(
        "fk_organisations_category_id_categories",
        "organisations",
        "categories",
        ["category_id"],
        ["id"],
    )

    op.add_column("organisations", sa.Column("address_line1", sa.String(length=255), nullable=True))
    op.add_column("organisations", sa.Column("address_line2", sa.String(length=255), nullable=True))
    op.add_column("organisations", sa.Column("city", sa.String(length=120), nullable=True))
    op.add_column("organisations", sa.Column("county_state", sa.String(length=120), nullable=True))
    op.add_column("organisations", sa.Column("postcode", sa.String(length=40), nullable=True))
    op.add_column("organisations", sa.Column("country", sa.String(length=80), nullable=True))

    op.add_column("organisations", sa.Column("contact_name", sa.String(length=255), nullable=True))
    op.add_column("organisations", sa.Column("contact_email", sa.String(length=255), nullable=True))
    op.add_column("organisations", sa.Column("contact_phone", sa.String(length=80), nullable=True))
    op.add_column("organisations", sa.Column("website", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("organisations", "website")
    op.drop_column("organisations", "contact_phone")
    op.drop_column("organisations", "contact_email")
    op.drop_column("organisations", "contact_name")

    op.drop_column("organisations", "country")
    op.drop_column("organisations", "postcode")
    op.drop_column("organisations", "county_state")
    op.drop_column("organisations", "city")
    op.drop_column("organisations", "address_line2")
    op.drop_column("organisations", "address_line1")

    op.drop_constraint("fk_organisations_category_id_categories", "organisations", type_="foreignkey")
    op.drop_index("ix_organisations_category_id", table_name="organisations")
    op.drop_column("organisations", "category_id")

    op.drop_index("ix_categories_slug", table_name="categories")
    op.drop_constraint("uq_categories_slug", "categories", type_="unique")
    op.drop_table("categories")

