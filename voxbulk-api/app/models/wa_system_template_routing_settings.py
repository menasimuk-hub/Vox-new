"""Platform routing for WA Survey + Customer Feedback system templates (local vs Meta sync)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TEMPLATE_SOURCE_LOCAL = "local"
TEMPLATE_SOURCE_META_SYNC = "meta_sync"


class WaSystemTemplateRoutingSettings(Base):
    __tablename__ = "wa_system_template_routing_settings"

    product: Mapped[str] = mapped_column(String(32), primary_key=True)
    template_source: Mapped[str] = mapped_column(String(32), nullable=False, default=TEMPLATE_SOURCE_LOCAL)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
