"""legal pages for platform settings

Revision ID: 0049_legal_pages
Revises: 0048_kb_file_scope
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049_legal_pages"
down_revision = "0048_kb_file_scope"
branch_labels = None
depends_on = None

DEFAULT_PAGES = [
    ("terms", "Terms & Conditions", "/terms", 1),
    ("privacy", "Privacy Policy", "/privacy", 2),
    ("cookies", "Cookie Policy", "/cookies", 3),
    ("gdpr", "GDPR", "/gdpr", 4),
    ("legal", "Legal", "/legal", 5),
]


def upgrade() -> None:
    op.create_table(
        "legal_pages",
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("public_path", sa.String(length=120), nullable=False),
        sa.Column("meta_description", sa.String(length=500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("slug"),
    )
    op.create_index("ix_legal_pages_is_published", "legal_pages", ["is_published"])
    op.create_index("ix_legal_pages_sort_order", "legal_pages", ["sort_order"])

    legal_pages = sa.table(
        "legal_pages",
        sa.column("slug", sa.String),
        sa.column("title", sa.String),
        sa.column("public_path", sa.String),
        sa.column("meta_description", sa.String),
        sa.column("body", sa.Text),
        sa.column("is_published", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        legal_pages,
        [
            {
                "slug": slug,
                "title": title,
                "public_path": path,
                "meta_description": None,
                "body": "",
                "is_published": True,
                "sort_order": sort_order,
            }
            for slug, title, path, sort_order in DEFAULT_PAGES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_legal_pages_sort_order", table_name="legal_pages")
    op.drop_index("ix_legal_pages_is_published", table_name="legal_pages")
    op.drop_table("legal_pages")
