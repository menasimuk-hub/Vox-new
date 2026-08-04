"""Widen voxbox message bodies to MEDIUMTEXT and longer subject/to fields.

MySQL TEXT is only 64KB; IMAP HTML bodies often exceed that and sync fails with
"Data too long for column" (user-facing: field too long for the database).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0224_voxbox_message_mediumtext"
down_revision = "0223_salesman_mail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.alter_column(
            "voxbox_messages",
            "body_text",
            existing_type=mysql.TEXT(),
            type_=mysql.MEDIUMTEXT(),
            existing_nullable=True,
        )
        op.alter_column(
            "voxbox_messages",
            "body_html",
            existing_type=mysql.TEXT(),
            type_=mysql.MEDIUMTEXT(),
            existing_nullable=True,
        )
    op.alter_column(
        "voxbox_messages",
        "to_addrs",
        existing_type=sa.String(length=1000),
        type_=sa.String(length=2000),
        existing_nullable=False,
    )
    op.alter_column(
        "voxbox_messages",
        "subject",
        existing_type=sa.String(length=500),
        type_=sa.String(length=998),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "voxbox_messages",
        "subject",
        existing_type=sa.String(length=998),
        type_=sa.String(length=500),
        existing_nullable=False,
    )
    op.alter_column(
        "voxbox_messages",
        "to_addrs",
        existing_type=sa.String(length=2000),
        type_=sa.String(length=1000),
        existing_nullable=False,
    )
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.alter_column(
            "voxbox_messages",
            "body_html",
            existing_type=mysql.MEDIUMTEXT(),
            type_=mysql.TEXT(),
            existing_nullable=True,
        )
        op.alter_column(
            "voxbox_messages",
            "body_text",
            existing_type=mysql.MEDIUMTEXT(),
            type_=mysql.TEXT(),
            existing_nullable=True,
        )
