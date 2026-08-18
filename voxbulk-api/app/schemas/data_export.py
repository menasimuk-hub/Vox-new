"""Manifest for organisation DSAR / portability ZIP (JSON files inside the archive)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DataExportManifest(BaseModel):
    export_version: str = "1"
    generated_at: datetime
    org_id: str
    requested_by_user_id: str
    files: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
