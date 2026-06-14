"""Join table: WA Survey industries visible to specific organisations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IndustryOrganisation(Base):
    __tablename__ = "industry_organisations"
    __table_args__ = (UniqueConstraint("industry_id", "org_id", name="uq_industry_organisations_industry_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    industry_id: Mapped[str] = mapped_column(String(36), ForeignKey("industries.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
