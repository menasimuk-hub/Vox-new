"""Add active_for_appointment flag for Appointment Manager WA templates."""

from alembic import op
import sqlalchemy as sa

revision = "0130_appointment_wa_templates"
down_revision = "0129_appointment_manager_foundation"
branch_labels = None
depends_on = None


def _column_exists(conn, table: str, column: str) -> bool:
    if conn.dialect.name == "sqlite":
        rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
        return any(str(r[1]) == column for r in rows)
    return (
        conn.execute(
            sa.text(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
            ),
            {"t": table, "c": column},
        ).fetchone()
        is not None
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "telnyx_whatsapp_templates", "active_for_appointment"):
        op.add_column(
            "telnyx_whatsapp_templates",
            sa.Column("active_for_appointment", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "telnyx_whatsapp_templates", "active_for_appointment"):
        op.drop_column("telnyx_whatsapp_templates", "active_for_appointment")
