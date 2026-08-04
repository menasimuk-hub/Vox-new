"""Optional DB override for Voxbox admin login (seeded from .env)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VoxboxAdminUser(Base):
    """Single-row admin credentials for the Voxbox app (id=1)."""

    __tablename__ = "voxbox_admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, default="admin", unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Admin")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
