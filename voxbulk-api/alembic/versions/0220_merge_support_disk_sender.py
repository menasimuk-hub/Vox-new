"""0220 — Merge Support Disk and platform sender password heads.

Revision ID: 0220_merge_support_disk_sender
Revises: 0219_support_disk, 0219_platform_sender_passwords
"""

from __future__ import annotations

revision = "0220_merge_support_disk_sender"
down_revision = ("0219_support_disk", "0219_platform_sender_passwords")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
