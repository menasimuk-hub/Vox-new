"""0208 — Expo wizard upgrades: contact email, offers, preview draft, visitor identity, mailbox.

Revision ID: 0208_expo_wizard_upgrades
Revises: 0207_ai_team_inbound_read_at
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0208_expo_wizard_upgrades"
down_revision = "0207_ai_team_inbound_read_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expo_booths", sa.Column("visitor_contact_email", sa.String(length=255), nullable=True))
    op.add_column("expo_booths", sa.Column("offer_config_json", sa.Text(), nullable=True))
    op.add_column(
        "expo_booths",
        sa.Column("is_preview_draft", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column(
        "expo_leads",
        sa.Column("offer_interested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("expo_leads", sa.Column("offer_claimed_at", sa.DateTime(), nullable=True))

    op.add_column(
        "expo_sessions",
        sa.Column("is_preview", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column(
        "expo_exhibitions",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/London"),
    )

    op.create_table(
        "expo_visitor_identities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False, index=True),
        sa.Column(
            "exhibition_id",
            sa.String(length=36),
            sa.ForeignKey("expo_exhibitions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("visitor_token", sa.String(length=64), nullable=False, index=True),
        sa.Column("visitor_phone", sa.String(length=64), nullable=True, index=True),
        sa.Column("visitor_email", sa.String(length=255), nullable=True, index=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("exhibition_id", "visitor_token", name="uq_expo_visitor_exhibition_token"),
    )

    op.create_table(
        "expo_org_profiles",
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), primary_key=True),
        sa.Column("visitor_contact_email", sa.String(length=255), nullable=True),
        sa.Column("representatives_json", sa.Text(), nullable=True),
        sa.Column("company_website", sa.String(length=512), nullable=True),
        sa.Column("notify_mobile", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "expo_mailbox_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "mailbox_email",
            sa.String(length=320),
            nullable=False,
            server_default="expo@voxbulk.com",
        ),
        sa.Column(
            "from_name",
            sa.String(length=255),
            nullable=False,
            server_default="VOXBULK Expo",
        ),
        sa.Column("smtp_username", sa.String(length=255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "expo_visitor_summary_sends",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("exhibition_id", sa.String(length=36), sa.ForeignKey("expo_exhibitions.id"), nullable=False, index=True),
        sa.Column("visitor_email", sa.String(length=255), nullable=False, index=True),
        sa.Column("summary_date", sa.String(length=16), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "exhibition_id",
            "visitor_email",
            "summary_date",
            "is_final",
            name="uq_expo_visitor_summary_send",
        ),
    )


def downgrade() -> None:
    op.drop_table("expo_visitor_summary_sends")
    op.drop_table("expo_mailbox_settings")
    op.drop_table("expo_org_profiles")
    op.drop_table("expo_visitor_identities")
    op.drop_column("expo_exhibitions", "timezone")
    op.drop_column("expo_sessions", "is_preview")
    op.drop_column("expo_leads", "offer_claimed_at")
    op.drop_column("expo_leads", "offer_interested")
    op.drop_column("expo_booths", "is_preview_draft")
    op.drop_column("expo_booths", "offer_config_json")
    op.drop_column("expo_booths", "visitor_contact_email")
