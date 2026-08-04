"""Salesman Mail models — labels, contacts, messages."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SalesMailLabel(Base):
    """Custom labels for salesman mail (like Gmail labels)."""

    __tablename__ = "sales_mail_labels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sales_rep_id: Mapped[str] = mapped_column(String(36), ForeignKey("sales_reps.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    color: Mapped[str] = mapped_column(String(32), nullable=False, default="#3b82f6")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SalesMailContact(Base):
    """Address book for salesman mail — auto-populated from customers + manual."""

    __tablename__ = "sales_mail_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sales_rep_id: Mapped[str] = mapped_column(String(36), ForeignKey("sales_reps.id"), nullable=False, index=True)
    sales_customer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sales_customers.id"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="", index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SalesMailMessage(Base):
    """Synced or sent messages for salesman mail."""

    __tablename__ = "sales_mail_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sales_rep_id: Mapped[str] = mapped_column(String(36), ForeignKey("sales_reps.id"), nullable=False, index=True)
    # IMAP folder + UID for sync
    folder: Mapped[str] = mapped_column(String(120), nullable=False, default="INBOX", index=True)
    uid: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    from_email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    from_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    to_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    cc_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # sent | received
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="received", index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    labels_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
