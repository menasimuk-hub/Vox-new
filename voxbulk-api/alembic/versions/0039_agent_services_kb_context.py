"""agent service assignments, kb_context, lead contact_name, frontpage org

Revision ID: 0039_agent_services_kb_context
Revises: 0038_agent_kb_and_call_workflow
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_agent_services_kb_context"
down_revision = "0038_agent_kb_and_call_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "agent_definitions" in tables:
        cols = {c["name"] for c in insp.get_columns("agent_definitions")}
        if "kb_context" not in cols:
            op.add_column("agent_definitions", sa.Column("kb_context", sa.Text(), nullable=True))

    if "frontpage_lead_calls" in tables:
        cols = {c["name"] for c in insp.get_columns("frontpage_lead_calls")}
        if "contact_name" not in cols:
            op.add_column("frontpage_lead_calls", sa.Column("contact_name", sa.String(255), nullable=True))

    if "frontpage_call_settings" in tables:
        cols = {c["name"] for c in insp.get_columns("frontpage_call_settings")}
        if "org_id" not in cols:
            op.add_column("frontpage_call_settings", sa.Column("org_id", sa.String(36), nullable=True))
            op.create_index("ix_frontpage_call_settings_org_id", "frontpage_call_settings", ["org_id"])

    if "agent_service_assignments" not in tables:
        op.create_table(
            "agent_service_assignments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("org_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
            sa.Column("service_key", sa.String(80), nullable=False),
            sa.Column("agent_id", sa.String(36), sa.ForeignKey("agent_definitions.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("org_id", "service_key", name="uq_agent_service_org_key"),
        )
        op.create_index("ix_agent_service_assignments_org_id", "agent_service_assignments", ["org_id"])
        op.create_index("ix_agent_service_assignments_service_key", "agent_service_assignments", ["service_key"])
        op.create_index("ix_agent_service_assignments_agent_id", "agent_service_assignments", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_service_assignments_agent_id", table_name="agent_service_assignments")
    op.drop_index("ix_agent_service_assignments_service_key", table_name="agent_service_assignments")
    op.drop_index("ix_agent_service_assignments_org_id", table_name="agent_service_assignments")
    op.drop_table("agent_service_assignments")
    op.drop_index("ix_frontpage_call_settings_org_id", table_name="frontpage_call_settings")
    op.drop_column("frontpage_call_settings", "org_id")
    op.drop_column("frontpage_lead_calls", "contact_name")
    op.drop_column("agent_definitions", "kb_context")
