from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_ref: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)

    organisation_id: Mapped[str] = mapped_column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("branches.id"), nullable=True, index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    priority: Mapped[str | None] = mapped_column(String(30), nullable=True)

    assigned_admin_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admin_users.id"), nullable=True, index=True)

    customer_unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    admin_unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    last_message_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SupportTicketMessage(Base):
    __tablename__ = "support_ticket_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("support_tickets.id"), nullable=False, index=True)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    sender_admin_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admin_users.id"), nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal_note: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SupportTicketAttachment(Base):
    __tablename__ = "support_ticket_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("support_tickets.id"), nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("support_ticket_messages.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SupportTicketEvent(Base):
    __tablename__ = "support_ticket_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("support_tickets.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="system")
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    actor_admin_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admin_users.id"), nullable=True)
    from_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class CannedReplyCategory(Base):
    __tablename__ = "support_canned_reply_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class CannedReply(Base):
    __tablename__ = "support_canned_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("support_canned_reply_categories.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

