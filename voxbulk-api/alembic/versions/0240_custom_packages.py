"""Custom multi-service packages tables.

Omit DB FKs on org_id for MySQL collation safety (indexes only) — same pattern as
0239_feedback_consent_events. Package PK/FK uses plain String(36).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0240_custom_packages"
down_revision = "0239_feedback_consent_events"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in sa.inspect(bind).get_table_names()


def _has_index(table: str, name: str) -> bool:
    bind = op.get_bind()
    if not _has_table(table):
        return False
    return any(ix["name"] == name for ix in sa.inspect(bind).get_indexes(table))


def upgrade() -> None:
    if not _has_table("custom_packages"):
        op.create_table(
            "custom_packages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("interval", sa.String(16), nullable=False, server_default="monthly"),
            sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
            sa.Column("price_minor", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
            sa.Column("admin_notes", sa.Text(), nullable=True),
            sa.Column("modules_json", sa.Text(), nullable=False),
            sa.Column("allowlist_json", sa.Text(), nullable=False),
            sa.Column("internal_cost_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if _has_table("custom_packages"):
        if not _has_index("custom_packages", "ix_custom_packages_code"):
            op.create_index("ix_custom_packages_code", "custom_packages", ["code"], unique=True)
        if not _has_index("custom_packages", "ix_custom_packages_status"):
            op.create_index("ix_custom_packages_status", "custom_packages", ["status"], unique=False)

    if not _has_table("custom_package_org_assignments"):
        op.create_table(
            "custom_package_org_assignments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("custom_package_id", sa.String(36), nullable=False),
            sa.Column("org_id", sa.String(36), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if _has_table("custom_package_org_assignments"):
        if not _has_index("custom_package_org_assignments", "ix_custom_pkg_assign_package"):
            op.create_index(
                "ix_custom_pkg_assign_package",
                "custom_package_org_assignments",
                ["custom_package_id"],
                unique=False,
            )
        if not _has_index("custom_package_org_assignments", "uq_custom_package_org_assignment_org"):
            op.create_index(
                "uq_custom_package_org_assignment_org",
                "custom_package_org_assignments",
                ["org_id"],
                unique=True,
            )
        if not _has_index("custom_package_org_assignments", "ix_custom_pkg_assign_org"):
            op.create_index(
                "ix_custom_pkg_assign_org",
                "custom_package_org_assignments",
                ["org_id"],
                unique=False,
            )


def downgrade() -> None:
    if _has_table("custom_package_org_assignments"):
        op.drop_table("custom_package_org_assignments")
    if _has_table("custom_packages"):
        op.drop_table("custom_packages")
