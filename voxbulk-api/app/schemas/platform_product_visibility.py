"""Schemas for platform product visibility registry."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlatformProductGroupIn(BaseModel):
    key: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    description: str = ""
    enabled: bool = True
    always_visible: bool = False
    sort_order: int = 200
    routes: list[str] = Field(default_factory=list)
    faq_category_slugs: list[str] = Field(default_factory=list)
    pricing_kinds: list[str] = Field(default_factory=list)


class PlatformProductGroupUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None
    routes: list[str] | None = None
    faq_category_slugs: list[str] | None = None
    pricing_kinds: list[str] | None = None


class PlatformProductGroupToggleIn(BaseModel):
    enabled: bool
