from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BranchCreate(BaseModel):
    name: str
    address_line1: str | None = None
    city: str | None = None
    postcode: str | None = None


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    name: str
    address_line1: str | None
    city: str | None
    postcode: str | None
    created_at: datetime

