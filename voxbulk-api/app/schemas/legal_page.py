from __future__ import annotations

from pydantic import BaseModel, Field


class LegalPageUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    meta_description: str | None = Field(default=None, max_length=500)
    body: str = ""
    is_published: bool = True


class LegalPageOut(BaseModel):
    slug: str
    title: str
    public_path: str
    meta_description: str | None = None
    body: str = ""
    is_published: bool = True
    sort_order: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}


class LegalPagePublicOut(BaseModel):
    slug: str
    title: str
    public_path: str
    meta_description: str | None = None
    body: str = ""
