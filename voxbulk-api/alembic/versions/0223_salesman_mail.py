"""Add salesman mail fields and tables (labels, contacts, messages)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0223_salesman_mail"
down_revision = "0222_support_requester_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add mailbox fields to sales_reps
    op.add_column("sales_reps", sa.Column("smtp_host", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("sales_reps", sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"))
    op.add_column("sales_reps", sa.Column("smtp_use_tls", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("sales_reps", sa.Column("smtp_use_ssl", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("sales_reps", sa.Column("smtp_username", sa.String(length=320), nullable=False, server_default=""))
    op.add_column("sales_reps", sa.Column("smtp_password_enc", sa.Text(), nullable=True))
    op.add_column("sales_reps", sa.Column("imap_host", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("sales_reps", sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"))
    op.add_column("sales_reps", sa.Column("imap_use_ssl", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("sales_reps", sa.Column("imap_use_tls", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("sales_reps", sa.Column("imap_username", sa.String(length=320), nullable=False, server_default=""))
    op.add_column("sales_reps", sa.Column("imap_password_enc", sa.Text(), nullable=True))
    op.add_column("sales_reps", sa.Column("email_signature", sa.Text(), nullable=False, server_default=""))

    # Create sales_mail_labels
    op.create_table(
        "sales_mail_labels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sales_rep_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("color", sa.String(length=32), nullable=False, server_default="#3b82f6"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["sales_rep_id"], ["sales_reps.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_mail_labels_sales_rep_id", "sales_mail_labels", ["sales_rep_id"])

    # Create sales_mail_contacts
    op.create_table(
        "sales_mail_contacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sales_rep_id", sa.String(length=36), nullable=False),
        sa.Column("sales_customer_id", sa.String(length=36), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["sales_rep_id"], ["sales_reps.id"]),
        sa.ForeignKeyConstraint(["sales_customer_id"], ["sales_customers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_mail_contacts_sales_rep_id", "sales_mail_contacts", ["sales_rep_id"])
    op.create_index("ix_sales_mail_contacts_sales_customer_id", "sales_mail_contacts", ["sales_customer_id"])
    op.create_index("ix_sales_mail_contacts_email", "sales_mail_contacts", ["email"])

    # Create sales_mail_messages
    op.create_table(
        "sales_mail_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sales_rep_id", sa.String(length=36), nullable=False),
        sa.Column("folder", sa.String(length=120), nullable=False, server_default="INBOX"),
        sa.Column("uid", sa.String(length=40), nullable=True),
        sa.Column("message_id", sa.String(length=320), nullable=True),
        sa.Column("from_email", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("from_name", sa.String(length=200), nullable=True),
        sa.Column("to_email", sa.Text(), nullable=True),
        sa.Column("cc_email", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("direction", sa.String(length=16), nullable=False, server_default="received"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_starred", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("labels_json", sa.Text(), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["sales_rep_id"], ["sales_reps.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_mail_messages_sales_rep_id", "sales_mail_messages", ["sales_rep_id"])
    op.create_index("ix_sales_mail_messages_folder", "sales_mail_messages", ["folder"])
    op.create_index("ix_sales_mail_messages_uid", "sales_mail_messages", ["uid"])
    op.create_index("ix_sales_mail_messages_message_id", "sales_mail_messages", ["message_id"])
    op.create_index("ix_sales_mail_messages_direction", "sales_mail_messages", ["direction"])
    op.create_index("ix_sales_mail_messages_date", "sales_mail_messages", ["date"])


def downgrade() -> None:
    # Drop sales_mail_messages
    op.drop_index("ix_sales_mail_messages_date", table_name="sales_mail_messages")
    op.drop_index("ix_sales_mail_messages_direction", table_name="sales_mail_messages")
    op.drop_index("ix_sales_mail_messages_message_id", table_name="sales_mail_messages")
    op.drop_index("ix_sales_mail_messages_uid", table_name="sales_mail_messages")
    op.drop_index("ix_sales_mail_messages_folder", table_name="sales_mail_messages")
    op.drop_index("ix_sales_mail_messages_sales_rep_id", table_name="sales_mail_messages")
    op.drop_table("sales_mail_messages")

    # Drop sales_mail_contacts
    op.drop_index("ix_sales_mail_contacts_email", table_name="sales_mail_contacts")
    op.drop_index("ix_sales_mail_contacts_sales_customer_id", table_name="sales_mail_contacts")
    op.drop_index("ix_sales_mail_contacts_sales_rep_id", table_name="sales_mail_contacts")
    op.drop_table("sales_mail_contacts")

    # Drop sales_mail_labels
    op.drop_index("ix_sales_mail_labels_sales_rep_id", table_name="sales_mail_labels")
    op.drop_table("sales_mail_labels")

    # Drop mailbox fields from sales_reps
    op.drop_column("sales_reps", "email_signature")
    op.drop_column("sales_reps", "imap_password_enc")
    op.drop_column("sales_reps", "imap_username")
    op.drop_column("sales_reps", "imap_use_tls")
    op.drop_column("sales_reps", "imap_use_ssl")
    op.drop_column("sales_reps", "imap_port")
    op.drop_column("sales_reps", "imap_host")
    op.drop_column("sales_reps", "smtp_password_enc")
    op.drop_column("sales_reps", "smtp_username")
    op.drop_column("sales_reps", "smtp_use_ssl")
    op.drop_column("sales_reps", "smtp_use_tls")
    op.drop_column("sales_reps", "smtp_port")
    op.drop_column("sales_reps", "smtp_host")
