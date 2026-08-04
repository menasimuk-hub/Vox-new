from __future__ import annotations

from pydantic import BaseModel, Field


class VoxboxLoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class VoxboxCredentialsUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    username: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)


class VoxboxAccountIn(BaseModel):
    name: str = Field(default="", max_length=120)
    email: str = Field(min_length=3, max_length=320)
    color: str = Field(default="var(--accent-1)", max_length=64)
    imap_host: str = Field(default="", max_length=255)
    imap_port: int = Field(default=993, ge=1, le=65535)
    smtp_host: str = Field(default="", max_length=255)
    smtp_port: int = Field(default=465, ge=1, le=65535)
    username: str = Field(default="", max_length=320)
    password: str | None = Field(default=None, max_length=500)
    ssl: bool = True
    smtp_use_ssl: bool | None = None
    smtp_use_tls: bool | None = None
    signature: str = Field(default="", max_length=4000)
    frozen: bool = False


class VoxboxAccountUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=320)
    color: str | None = Field(default=None, max_length=64)
    imap_host: str | None = Field(default=None, max_length=255)
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=320)
    password: str | None = Field(default=None, max_length=500)
    ssl: bool | None = None
    smtp_use_ssl: bool | None = None
    smtp_use_tls: bool | None = None
    signature: str | None = Field(default=None, max_length=4000)
    frozen: bool | None = None


class VoxboxReorderIn(BaseModel):
    ordered_ids: list[str] = Field(default_factory=list)


class VoxboxMessagePatch(BaseModel):
    unread: bool | None = None
    starred: bool | None = None
    important: bool | None = None
    folder: str | None = Field(default=None, max_length=32)


class VoxboxSendIn(BaseModel):
    kind: str = Field(default="reply", pattern="^(reply|forward)$")
    body: str = Field(min_length=1, max_length=50000)
    to: str | None = Field(default=None, max_length=1000)


class VoxboxAiReplyIn(BaseModel):
    subject: str = Field(default="", max_length=400)
    from_: str = Field(default="", alias="from", max_length=200)
    body: str = Field(default="", max_length=6000)
    tone: str = Field(default="professional", max_length=40)
    mode: str = Field(default="write", pattern="^(write|fix)$")
    draft: str = Field(default="", max_length=6000)

    model_config = {"populate_by_name": True}
