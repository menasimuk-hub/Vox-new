from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_identities_provider_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # google/apple/linkedin
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

