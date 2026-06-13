"""HubSpot contact sync pool (org-scoped, v1 beta)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0120_hubspot_contacts"
down_revision = "0119_customer_feedback_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hubspot_contacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("hubspot_contact_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("raw_properties_json", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "hubspot_contact_id", name="uq_hubspot_contacts_org_hs_id"),
    )
    op.create_index("ix_hubspot_contacts_org_id", "hubspot_contacts", ["org_id"])
    op.create_index("ix_hubspot_contacts_hubspot_contact_id", "hubspot_contacts", ["hubspot_contact_id"])
    op.create_index("ix_hubspot_contacts_email", "hubspot_contacts", ["email"])
    op.create_index("ix_hubspot_contacts_phone", "hubspot_contacts", ["phone"])


def downgrade() -> None:
    op.drop_table("hubspot_contacts")
