from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FAQCategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str | None = Field(default=None, max_length=180)
    sort_order: int = 0


class FAQItemIn(BaseModel):
    category_id: int | None = None
    question: str = Field(min_length=3, max_length=5000)
    answer: str = Field(min_length=3, max_length=20000)
    is_featured: bool = False
    is_published: bool = True
    sort_order: int = 0


class FAQCategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    sort_order: int
    created_at: datetime


class FAQItemOut(BaseModel):
    id: int
    category_id: int | None = None
    category_name: str | None = None
    question: str
    answer: str
    is_featured: bool
    is_published: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class FAQCategoryWithItemsOut(FAQCategoryOut):
    items: list[FAQItemOut] = []

