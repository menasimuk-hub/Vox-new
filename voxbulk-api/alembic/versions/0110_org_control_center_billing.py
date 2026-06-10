"""Organisation control center — country_code, overage flag, audit metadata, invoice email status."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0110_org_control_center_billing"
down_revision = "0109_billing_system_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organisations", sa.Column("country_code", sa.String(length=2), nullable=True))
    op.add_column(
        "organisations",
        sa.Column("allow_overage", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_organisations_country_code", "organisations", ["country_code"])

    op.add_column("organisation_audit_events", sa.Column("event_type", sa.String(length=80), nullable=True))
    op.add_column("organisation_audit_events", sa.Column("entity_type", sa.String(length=40), nullable=True))
    op.add_column("organisation_audit_events", sa.Column("entity_id", sa.String(length=36), nullable=True))
    op.add_column("organisation_audit_events", sa.Column("metadata_json", sa.Text(), nullable=True))
    op.create_index("ix_org_audit_events_event_type", "organisation_audit_events", ["event_type"])

    op.add_column(
        "billing_invoices",
        sa.Column("invoice_email_status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.add_column("billing_invoices", sa.Column("invoice_email_last_error", sa.Text(), nullable=True))
    op.add_column("billing_invoices", sa.Column("invoice_email_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("billing_invoices", "invoice_email_attempts")
    op.drop_column("billing_invoices", "invoice_email_last_error")
    op.drop_column("billing_invoices", "invoice_email_status")
    op.drop_index("ix_org_audit_events_event_type", table_name="organisation_audit_events")
    op.drop_column("organisation_audit_events", "metadata_json")
    op.drop_column("organisation_audit_events", "entity_type")
    op.drop_column("organisation_audit_events", "entity_id")
    op.drop_column("organisation_audit_events", "event_type")
    op.drop_index("ix_organisations_country_code", table_name="organisations")
    op.drop_column("organisations", "allow_overage")
    op.drop_column("organisations", "country_code")
