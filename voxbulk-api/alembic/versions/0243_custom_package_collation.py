"""Align custom_package string columns to organisations.id collation.

Fixes MySQL 1267 illegal mix of collations on joins
(custom_package_org_assignments.org_id = organisations.id).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0243_custom_package_collation"
down_revision = "0242_merge_custom_packages_heads"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    return table in sa.inspect(bind).get_table_names()


def _column_collation(table: str, column: str) -> str | None:
    bind = op.get_bind()
    try:
        return bind.execute(
            sa.text(
                "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = :table AND COLUMN_NAME = :column "
                "LIMIT 1"
            ),
            {"table": table, "column": column},
        ).scalar()
    except Exception:
        return None


def _mysql_modify(table: str, column: str, definition: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    op.execute(sa.text(f"ALTER TABLE `{table}` MODIFY COLUMN `{column}` {definition}"))


def upgrade() -> None:
    org_collation = _column_collation("organisations", "id") or "utf8mb4_unicode_ci"
    charset = "utf8mb4"

    if _has_table("custom_packages"):
        for col, length, nullable in (
            ("id", 36, "NOT NULL"),
            ("name", 255, "NOT NULL"),
            ("code", 64, "NOT NULL"),
            ("interval", 16, "NOT NULL"),
            ("currency", 3, "NOT NULL"),
            ("status", 16, "NOT NULL"),
        ):
            _mysql_modify(
                "custom_packages",
                col,
                f"VARCHAR({length}) CHARACTER SET {charset} COLLATE {org_collation} {nullable}",
            )

    if _has_table("custom_package_org_assignments"):
        for col, length, nullable in (
            ("id", 36, "NOT NULL"),
            ("custom_package_id", 36, "NOT NULL"),
            ("org_id", 36, "NOT NULL"),
        ):
            _mysql_modify(
                "custom_package_org_assignments",
                col,
                f"VARCHAR({length}) CHARACTER SET {charset} COLLATE {org_collation} {nullable}",
            )


def downgrade() -> None:
    # Collation alignment is forward-only; no safe downgrade on mixed VPS DBs.
    pass
