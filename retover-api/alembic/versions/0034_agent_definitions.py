"""agent definitions and assignments

Revision ID: 0034_agent_definitions
Revises: 0033_telnyx_voice_agent_fields
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0034_agent_definitions"
down_revision = "0033_telnyx_voice_agent_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "agent_definitions" not in tables:
        op.create_table(
            "agent_definitions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=120), nullable=False),
            sa.Column("business_type", sa.String(length=120), nullable=True),
            sa.Column("category_id", sa.String(length=36), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("system_prompt", sa.Text(), nullable=False),
            sa.Column("conversation_style", sa.Text(), nullable=True),
            sa.Column("default_model", sa.String(length=120), nullable=True),
            sa.Column("default_voice", sa.String(length=120), nullable=True),
            sa.Column("use_azure_tts", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("use_azure_stt", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("allow_booking_tool", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("allow_lookup_tool", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("allow_reschedule_tool", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("allow_cancel_tool", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )
        op.create_index("ix_agent_definitions_slug", "agent_definitions", ["slug"])
        op.create_index("ix_agent_definitions_business_type", "agent_definitions", ["business_type"])
        op.create_index("ix_agent_definitions_category_id", "agent_definitions", ["category_id"])

    if "agent_assignments" not in tables:
        op.create_table(
            "agent_assignments",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("agent_id", sa.String(length=36), nullable=False),
            sa.Column("org_id", sa.String(length=36), nullable=True),
            sa.Column("category_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["agent_id"], ["agent_definitions.id"]),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
            sa.ForeignKeyConstraint(["org_id"], ["organisations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("org_id", name="uq_agent_assignment_org"),
            sa.UniqueConstraint("category_id", name="uq_agent_assignment_category"),
        )
        op.create_index("ix_agent_assignments_agent_id", "agent_assignments", ["agent_id"])
        op.create_index("ix_agent_assignments_org_id", "agent_assignments", ["org_id"])
        op.create_index("ix_agent_assignments_category_id", "agent_assignments", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_assignments_category_id", table_name="agent_assignments")
    op.drop_index("ix_agent_assignments_org_id", table_name="agent_assignments")
    op.drop_index("ix_agent_assignments_agent_id", table_name="agent_assignments")
    op.drop_table("agent_assignments")
    op.drop_index("ix_agent_definitions_category_id", table_name="agent_definitions")
    op.drop_index("ix_agent_definitions_business_type", table_name="agent_definitions")
    op.drop_index("ix_agent_definitions_slug", table_name="agent_definitions")
    op.drop_table("agent_definitions")
