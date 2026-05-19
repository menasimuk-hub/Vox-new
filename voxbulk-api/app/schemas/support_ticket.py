from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


TicketCategory = str
TicketStatus = str


class TicketCreateIn(BaseModel):
    category: TicketCategory
    subject: str = Field(min_length=3, max_length=255)
    message: str = Field(min_length=2, max_length=10000)
    branch_id: str | None = None
    priority: str | None = None


class TicketReplyIn(BaseModel):
    message: str = Field(min_length=2, max_length=10000)
    is_internal_note: bool = False


class TicketStatusUpdateIn(BaseModel):
    status: TicketStatus


class TicketAssignIn(BaseModel):
    assigned_admin_user_id: str | None = None


class TicketOut(BaseModel):
    id: int
    public_ref: str
    organisation_id: str
    organisation_name: str | None = None
    branch_id: str | None = None
    branch_name: str | None = None
    created_by_user_id: str
    created_by_email: str | None = None
    category: str
    subject: str
    status: str
    priority: str | None = None
    assigned_admin_user_id: str | None = None
    assigned_admin_email: str | None = None
    customer_unread: bool
    admin_unread: bool
    last_message_at: datetime
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TicketMessageOut(BaseModel):
    id: int
    ticket_id: int
    sender_type: str
    sender_user_id: str | None = None
    sender_admin_user_id: str | None = None
    sender_email: str | None = None
    body: str
    is_internal_note: bool
    created_at: datetime


class TicketAttachmentOut(BaseModel):
    id: int
    ticket_id: int
    message_id: int
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class TicketEventOut(BaseModel):
    id: int
    ticket_id: int
    event_type: str
    actor_type: str
    from_value: str | None = None
    to_value: str | None = None
    created_at: datetime


class TicketDetailOut(BaseModel):
    ticket: TicketOut
    messages: list[TicketMessageOut]
    events: list[TicketEventOut] = []


class TicketKpiOut(BaseModel):
    total_open: int
    total_pending: int
    total_closed: int
    unassigned: int
    technical_open: int
    invoices_open: int
    pre_sale_open: int
    overdue: int


class CannedReplyCategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None


class CannedReplyIn(BaseModel):
    category_id: int | None = None
    title: str = Field(min_length=2, max_length=180)
    question: str = Field(min_length=2, max_length=5000)
    answer: str = Field(min_length=2, max_length=10000)
    is_active: bool = True


class CannedReplyCategoryOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class CannedReplyOut(BaseModel):
    id: int
    category_id: int | None = None
    category_name: str | None = None
    title: str
    question: str
    answer: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

