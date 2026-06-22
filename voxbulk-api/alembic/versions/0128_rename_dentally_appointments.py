"""Rename legacy appointments table to dentally_appointments; retarget recovery FKs."""

from alembic import op
import sqlalchemy as sa

revision = "0128_rename_dentally_appointments"
down_revision = "0127_billing_mailbox_settings"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _table_exists("appointments"):
        return
    if _table_exists("dentally_appointments"):
        return

    op.rename_table("appointments", "dentally_appointments")

    for table in ("recovery_jobs", "call_logs", "whatsapp_logs"):
        if not _table_exists(table):
            continue
        if _column_exists(table, "appointment_id") and not _column_exists(table, "dentally_appointment_id"):
            op.alter_column(table, "appointment_id", new_column_name="dentally_appointment_id", existing_type=sa.String(36))
            idx_old = f"ix_{table}_appointment_id"
            idx_new = f"ix_{table}_dentally_appointment_id"
            bind = op.get_bind()
            insp = sa.inspect(bind)
            if any(i.get("name") == idx_old for i in insp.get_indexes(table)):
                op.execute(sa.text(f"ALTER TABLE `{table}` RENAME INDEX `{idx_old}` TO `{idx_new}`"))


def downgrade() -> None:
    if _table_exists("dentally_appointments") and not _table_exists("appointments"):
        op.rename_table("dentally_appointments", "appointments")

    for table in ("recovery_jobs", "call_logs", "whatsapp_logs"):
        if not _table_exists(table):
            continue
        if _column_exists(table, "dentally_appointment_id") and not _column_exists(table, "appointment_id"):
            op.alter_column(table, "dentally_appointment_id", new_column_name="appointment_id", existing_type=sa.String(36))
