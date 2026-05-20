"""knowledge base file scope (lead / sales / org)

Revision ID: 0048_kb_file_scope
Revises: 0047_email_template_html_defaults
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0048_kb_file_scope"
down_revision = "0047_email_template_html_defaults"
branch_labels = None
depends_on = None


def _parse_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def upgrade() -> None:
    op.add_column(
        "knowledge_base_files",
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="org"),
    )
    op.create_index("ix_knowledge_base_files_scope", "knowledge_base_files", ["scope"])

    conn = op.get_bind()

    lead_ids: set[str] = set()
    try:
        row = conn.execute(sa.text("SELECT kb_file_ids FROM frontpage_call_settings WHERE id = 'default' LIMIT 1")).fetchone()
        if row and row[0]:
            lead_ids.update(_parse_ids(row[0]))
    except Exception:
        pass

    sales_ids: set[str] = set()
    try:
        row = conn.execute(sa.text("SELECT kb_file_ids FROM lead_sales_settings WHERE id = 'default' LIMIT 1")).fetchone()
        if row and row[0]:
            sales_ids.update(_parse_ids(row[0]))
    except Exception:
        pass

    for fid in lead_ids:
        conn.execute(
            sa.text("UPDATE knowledge_base_files SET scope = 'lead' WHERE id = :id"),
            {"id": fid},
        )
    for fid in sales_ids - lead_ids:
        conn.execute(
            sa.text("UPDATE knowledge_base_files SET scope = 'sales' WHERE id = :id"),
            {"id": fid},
        )


def downgrade() -> None:
    op.drop_index("ix_knowledge_base_files_scope", table_name="knowledge_base_files")
    op.drop_column("knowledge_base_files", "scope")
