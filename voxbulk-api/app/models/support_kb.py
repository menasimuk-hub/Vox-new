from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupportKbCategory(Base):
    __tablename__ = "support_kb_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="article", index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slug: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    colour: Mapped[str] = mapped_column(String(40), nullable=False, default="#3b82f6")
    linked_service: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SupportKbArticle(Base):
    __tablename__ = "support_kb_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("support_kb_categories.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="article", index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    author: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    linked_service: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SupportHelpLink(Base):
    __tablename__ = "support_help_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    seed_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True, index=True)
    linked_service: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SupportSlaSettings(Base):
    __tablename__ = "support_sla_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_response_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    resolve_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=48)
    waiting_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
