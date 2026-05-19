"""add branch/patient/appointment/log tables

Revision ID: 0002_add_branch_patient_appointment_logs
Revises: 0001_init_core_tables
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_add_branch_patient_appointment_logs"
down_revision = "0001_init_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("postcode", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_branches_org_id", "branches", ["org_id"], unique=False)

    op.create_table(
        "patients",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("phone_e164", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_patients_org_id", "patients", ["org_id"], unique=False)
    op.create_index("ix_patients_branch_id", "patients", ["branch_id"], unique=False)
    op.create_index("ix_patients_phone_e164", "patients", ["phone_e164"], unique=False)
    op.create_index("ix_patients_email", "patients", ["email"], unique=False)

    op.create_table(
        "appointments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("branch_id", sa.String(length=36), sa.ForeignKey("branches.id"), nullable=True),
        sa.Column("patient_id", sa.String(length=36), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("scheduled_start", sa.DateTime(), nullable=False),
        sa.Column("scheduled_end", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_appointments_org_id", "appointments", ["org_id"], unique=False)
    op.create_index("ix_appointments_branch_id", "appointments", ["branch_id"], unique=False)
    op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"], unique=False)
    op.create_index("ix_appointments_scheduled_start", "appointments", ["scheduled_start"], unique=False)

    op.create_table(
        "call_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("appointment_id", sa.String(length=36), sa.ForeignKey("appointments.id"), nullable=True),
        sa.Column("patient_id", sa.String(length=36), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("to_number", sa.String(length=32), nullable=True),
        sa.Column("from_number", sa.String(length=32), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_call_logs_org_id", "call_logs", ["org_id"], unique=False)
    op.create_index("ix_call_logs_appointment_id", "call_logs", ["appointment_id"], unique=False)
    op.create_index("ix_call_logs_patient_id", "call_logs", ["patient_id"], unique=False)

    op.create_table(
        "whatsapp_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("appointment_id", sa.String(length=36), sa.ForeignKey("appointments.id"), nullable=True),
        sa.Column("patient_id", sa.String(length=36), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("to_number", sa.String(length=32), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_whatsapp_logs_org_id", "whatsapp_logs", ["org_id"], unique=False)
    op.create_index("ix_whatsapp_logs_appointment_id", "whatsapp_logs", ["appointment_id"], unique=False)
    op.create_index("ix_whatsapp_logs_patient_id", "whatsapp_logs", ["patient_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_whatsapp_logs_patient_id", table_name="whatsapp_logs")
    op.drop_index("ix_whatsapp_logs_appointment_id", table_name="whatsapp_logs")
    op.drop_index("ix_whatsapp_logs_org_id", table_name="whatsapp_logs")
    op.drop_table("whatsapp_logs")

    op.drop_index("ix_call_logs_patient_id", table_name="call_logs")
    op.drop_index("ix_call_logs_appointment_id", table_name="call_logs")
    op.drop_index("ix_call_logs_org_id", table_name="call_logs")
    op.drop_table("call_logs")

    op.drop_index("ix_appointments_scheduled_start", table_name="appointments")
    op.drop_index("ix_appointments_patient_id", table_name="appointments")
    op.drop_index("ix_appointments_branch_id", table_name="appointments")
    op.drop_index("ix_appointments_org_id", table_name="appointments")
    op.drop_table("appointments")

    op.drop_index("ix_patients_email", table_name="patients")
    op.drop_index("ix_patients_phone_e164", table_name="patients")
    op.drop_index("ix_patients_branch_id", table_name="patients")
    op.drop_index("ix_patients_org_id", table_name="patients")
    op.drop_table("patients")

    op.drop_index("ix_branches_org_id", table_name="branches")
    op.drop_table("branches")

