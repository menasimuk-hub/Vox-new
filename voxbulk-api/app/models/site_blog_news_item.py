from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SiteBlogNewsItem(Base):
    """Marketing-site blog essays and newsroom announcements."""

    __tablename__ = "site_blog_news_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # blog | news
    slug: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="General")
    author: Mapped[str] = mapped_column(String(120), nullable=False, default="VoxBulk")
    author_role: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="text")  # text | html
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published_at: Mapped[date] = mapped_column(Date, nullable=False)
    read_mins: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
