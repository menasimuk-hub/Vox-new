from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field


class SmtpSettingsUpdate(BaseModel):
    host: str = Field(default="")
    port: int = Field(default=587, ge=1, le=65535)
    username: str | None = Field(default="")
    # Send a new value to rotate; omit field or send null/blank to keep existing.
    password: str | None = None
    from_name: str = Field(default="")
    from_email: str = Field(default="")
    use_tls: bool = True
    use_ssl: bool = False
    is_enabled: bool = False


class SmtpTestSendRequest(BaseModel):
    to: EmailStr


class EmailTemplateUpdate(BaseModel):
    title: str | None = None
    subject: str = Field(default="")
    body: str = Field(default="")
    is_enabled: bool = True


class EmailTemplateCreate(BaseModel):
    template_key: str = Field(min_length=3, max_length=64)
    title: str = Field(default="")
    subject: str = Field(default="")
    body: str = Field(default="")
    is_enabled: bool = True


class ChannelTemplateCreate(BaseModel):
    template_key: str = Field(min_length=3, max_length=64)
    name: str = Field(default="")
    body: str = Field(default="")
    is_enabled: bool = True


class ChannelTemplateUpdate(BaseModel):
    name: str = Field(default="")
    body: str = Field(default="")
    is_enabled: bool = True


class TemplatedNotifySendRequest(BaseModel):
    """Admin/dev: exercise product notification templates (excluding password reset)."""

    template_key: str = Field(min_length=3, max_length=64)
    to: EmailStr
    variables: dict[str, Any] = Field(default_factory=dict)


class EmailTemplateTestSendRequest(BaseModel):
    """Send a one-off test using template content (saved or draft) with dummy variables."""

    to: EmailStr
    subject: str | None = None
    body: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
