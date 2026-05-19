"""agent call_workflow and knowledge base library

Revision ID: 0038_agent_kb_and_call_workflow
Revises: 0037_frontpage_call_settings
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0038_agent_kb_and_call_workflow"
down_revision = "0037_frontpage_call_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "agent_definitions" in tables:
        cols = {c["name"] for c in inspector.get_columns("agent_definitions")}
        if "call_workflow" not in cols:
            op.add_column("agent_definitions", sa.Column("call_workflow", sa.Text(), nullable=True))

    if "knowledge_base_files" not in tables:
        op.create_table(
            "knowledge_base_files",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("storage_path", sa.String(length=512), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("storage_path"),
        )
        op.create_index("ix_knowledge_base_files_storage_path", "knowledge_base_files", ["storage_path"], unique=True)
        op.create_index("ix_knowledge_base_files_uploaded_by_user_id", "knowledge_base_files", ["uploaded_by_user_id"])

    if "agent_knowledge_files" not in tables:
        op.create_table(
            "agent_knowledge_files",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("agent_id", sa.String(length=36), nullable=False),
            sa.Column("knowledge_base_file_id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["agent_id"], ["agent_definitions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["knowledge_base_file_id"], ["knowledge_base_files.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("agent_id", "knowledge_base_file_id", name="uq_agent_kb_file"),
        )
        op.create_index("ix_agent_knowledge_files_agent_id", "agent_knowledge_files", ["agent_id"])
        op.create_index("ix_agent_knowledge_files_knowledge_base_file_id", "agent_knowledge_files", ["knowledge_base_file_id"])


def downgrade() -> None:
    op.drop_table("agent_knowledge_files")
    op.drop_table("knowledge_base_files")
    op.drop_column("agent_definitions", "call_workflow")
