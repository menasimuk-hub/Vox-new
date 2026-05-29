"""Org opt-out list and customer audit log.

Revision ID: 0079_org_opt_out_audit_team
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0079_org_opt_out_audit_team"
down_revision = "0078_org_allowed_services"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organisation_opt_outs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("phone_e164", sa.String(length=32), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "phone_e164", name="uq_org_opt_out_phone"),
    )
    op.create_index("ix_organisation_opt_outs_org_id", "organisation_opt_outs", ["org_id"], unique=False)
    op.create_index("ix_organisation_opt_outs_phone_e164", "organisation_opt_outs", ["phone_e164"], unique=False)

    op.create_table(
        "organisation_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organisation_audit_events_org_id", "organisation_audit_events", ["org_id"], unique=False)
    op.create_index("ix_organisation_audit_events_created_at", "organisation_audit_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_organisation_audit_events_created_at", table_name="organisation_audit_events")
    op.drop_index("ix_organisation_audit_events_org_id", table_name="organisation_audit_events")
    op.drop_table("organisation_audit_events")
    op.drop_index("ix_organisation_opt_outs_phone_e164", table_name="organisation_opt_outs")
    op.drop_index("ix_organisation_opt_outs_org_id", table_name="organisation_opt_outs")
    op.drop_table("organisation_opt_outs")
