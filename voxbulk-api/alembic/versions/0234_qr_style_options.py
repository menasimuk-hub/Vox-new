"""Add QR style columns for Smart Card, Expo, and Customer Feedback."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0234_qr_style_options"
down_revision = "0233_org_logo_tone"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    if table not in sa.inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _add(table: str, column: str, col: sa.Column) -> None:
    if not _has_column(table, column):
        op.add_column(table, col)


def upgrade() -> None:
    # Smart Card — already has colours / transparent
    _add(
        "smart_card_representatives",
        "qr_module_style",
        sa.Column("qr_module_style", sa.String(length=16), nullable=False, server_default="square"),
    )
    _add(
        "smart_card_representatives",
        "qr_corner_style",
        sa.Column("qr_corner_style", sa.String(length=16), nullable=False, server_default="square"),
    )
    _add(
        "smart_card_representatives",
        "qr_show_arrow",
        sa.Column("qr_show_arrow", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _add(
        "smart_card_representatives",
        "qr_frame_round",
        sa.Column("qr_frame_round", sa.String(length=16), nullable=False, server_default="none"),
    )

    for table in ("expo_booths", "feedback_locations"):
        _add(table, "qr_fg_color", sa.Column("qr_fg_color", sa.String(length=16), nullable=False, server_default="000000"))
        _add(table, "qr_bg_color", sa.Column("qr_bg_color", sa.String(length=16), nullable=False, server_default="ffffff"))
        _add(
            table,
            "qr_module_style",
            sa.Column("qr_module_style", sa.String(length=16), nullable=False, server_default="square"),
        )
        _add(
            table,
            "qr_corner_style",
            sa.Column("qr_corner_style", sa.String(length=16), nullable=False, server_default="square"),
        )
        _add(table, "qr_show_arrow", sa.Column("qr_show_arrow", sa.Boolean(), nullable=False, server_default=sa.false()))
        _add(
            table,
            "qr_frame_round",
            sa.Column("qr_frame_round", sa.String(length=16), nullable=False, server_default="none"),
        )


def downgrade() -> None:
    for col in ("qr_frame_round", "qr_show_arrow", "qr_corner_style", "qr_module_style"):
        if _has_column("smart_card_representatives", col):
            op.drop_column("smart_card_representatives", col)
    for table in ("expo_booths", "feedback_locations"):
        for col in (
            "qr_frame_round",
            "qr_show_arrow",
            "qr_corner_style",
            "qr_module_style",
            "qr_bg_color",
            "qr_fg_color",
        ):
            if _has_column(table, col):
                op.drop_column(table, col)
