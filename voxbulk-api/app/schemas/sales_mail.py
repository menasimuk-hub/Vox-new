"""Salesman mail request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SalesMailEscalateTarget = Literal["support", "billing"]


class SalesMailAttachmentIn(BaseModel):
    filename: str | None = None
    name: str | None = None
    content_type: str | None = "application/octet-stream"
    data_base64: str | None = None
    dataBase64: str | None = None


class SalesMailSendIn(BaseModel):
    to: str = Field(default="", max_length=2000)
    subject: str = Field(default="", max_length=500)
    body_html: str | None = None
    body_text: str | None = None
    cc: str | None = None
    insert_promo: bool = False
    attachments: list[SalesMailAttachmentIn] | list[dict[str, Any]] | None = None
    # When set, send SMTP then create a support ticket (idempotent via fingerprint).
    escalate_target: SalesMailEscalateTarget | None = None
    source_message_id: str | None = Field(default=None, max_length=36)


class SalesMailEscalateIn(BaseModel):
    """Typed escalate payload (same send path; target required)."""

    escalate_target: SalesMailEscalateTarget
    source_message_id: str = Field(min_length=1, max_length=36)
    subject: str | None = Field(default=None, max_length=500)
    body_html: str | None = None
    body_text: str | None = None
    cc: str | None = None
    attachments: list[SalesMailAttachmentIn] | list[dict[str, Any]] | None = None
