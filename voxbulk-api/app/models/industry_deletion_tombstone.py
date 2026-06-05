"""Slugs admin deleted — block idempotent seeders from recreating them."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IndustryDeletionTombstone(Base):
    __tablename__ = "industry_deletion_tombstones"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
