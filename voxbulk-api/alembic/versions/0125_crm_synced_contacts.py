"""CRM synced contacts pool (Pipedrive, Zoho CRM)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0125_crm_synced_contacts"
down_revision = "0124_wave2_crm_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_synced_contacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("external_contact_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("raw_properties_json", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "org_id",
            "provider",
            "external_contact_id",
            name="uq_crm_synced_contacts_org_provider_ext",
        ),
    )
    op.create_index("ix_crm_synced_contacts_org_id", "crm_synced_contacts", ["org_id"])
    op.create_index("ix_crm_synced_contacts_provider", "crm_synced_contacts", ["provider"])
    op.create_index("ix_crm_synced_contacts_external_contact_id", "crm_synced_contacts", ["external_contact_id"])
    op.create_index("ix_crm_synced_contacts_email", "crm_synced_contacts", ["email"])
    op.create_index("ix_crm_synced_contacts_phone", "crm_synced_contacts", ["phone"])


def downgrade() -> None:
    op.drop_table("crm_synced_contacts")
