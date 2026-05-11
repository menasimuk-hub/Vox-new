"""Repair organisations row shape when alembic_version is ahead of actual SQLite DDL (dev drift).

Revision ID: 0023_repair_organisations_schema_drift
Revises: 0022_admin_users_and_billing_email_events
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0023_repair_organisations_schema_drift"
down_revision = "0022_admin_users_billing_events"
branch_labels = None
depends_on = None


def _org_columns(bind) -> set[str]:
    insp = sa.inspect(bind)
    if not insp.has_table("organisations"):
        return set()
    return {c["name"] for c in insp.get_columns("organisations")}


def _ensure_categories(bind) -> None:
    insp = sa.inspect(bind)
    if insp.has_table("categories"):
        return
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


def upgrade() -> None:
    bind = op.get_bind()
    cols = _org_columns(bind)

    _ensure_categories(bind)

    # 0016_org_suspended_profile_notes (may be missing when version table was bumped without DDL)
    if "is_suspended" not in cols:
        op.add_column(
            "organisations",
            sa.Column("is_suspended", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "profile_notes" not in cols:
        op.add_column("organisations", sa.Column("profile_notes", sa.Text(), nullable=True))

    cols = _org_columns(bind)

    # 0018 profile / category linkage
    if "category_id" not in cols:
        op.add_column("organisations", sa.Column("category_id", sa.String(length=36), nullable=True))
        op.create_index("ix_organisations_category_id", "organisations", ["category_id"], unique=False)
        # FK optional for SQLite repair (table may already have rows); add if SQLite allows
        try:
            op.create_foreign_key(
                "fk_organisations_category_id_categories",
                "organisations",
                "categories",
                ["category_id"],
                ["id"],
            )
        except Exception:
            pass

    cols = _org_columns(bind)

    for colname, typ in (
        ("address_line1", sa.String(255)),
        ("address_line2", sa.String(255)),
        ("city", sa.String(120)),
        ("county_state", sa.String(120)),
        ("postcode", sa.String(40)),
        ("country", sa.String(80)),
        ("contact_name", sa.String(255)),
        ("contact_email", sa.String(255)),
        ("contact_phone", sa.String(80)),
        ("website", sa.String(255)),
    ):
        if colname not in cols:
            op.add_column("organisations", sa.Column(colname, typ, nullable=True))


def downgrade() -> None:
    # Non-destructive repair migration: no downgrade
    pass
