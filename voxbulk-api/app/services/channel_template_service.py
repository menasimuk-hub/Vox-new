from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Type

from sqlalchemy import select
from sqlalchemy.orm import Session

_TEMPLATE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class ChannelTemplateError(ValueError):
    pass


class ChannelTemplateService:
    @staticmethod
    def normalize_key(key: str) -> str:
        k = (key or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not _TEMPLATE_KEY_RE.match(k):
            raise ChannelTemplateError("Template key must be 3–64 chars: lowercase letters, numbers, underscores; start with a letter.")
        return k

    @staticmethod
    def list_all(db: Session, *, model) -> list[dict[str, Any]]:
        rows = db.execute(select(model).order_by(model.template_key.asc())).scalars().all()
        return [ChannelTemplateService.to_dict(r) for r in rows]

    @staticmethod
    def get(db: Session, *, model, key: str):
        k = ChannelTemplateService.normalize_key(key)
        return db.execute(select(model).where(model.template_key == k)).scalar_one_or_none()

    @staticmethod
    def to_dict(row) -> dict[str, Any]:
        return {
            "id": row.id,
            "template_key": row.template_key,
            "name": row.name or "",
            "body": row.body or "",
            "is_enabled": bool(row.is_enabled),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def create(db: Session, *, model, key: str, name: str, body: str, is_enabled: bool = True):
        k = ChannelTemplateService.normalize_key(key)
        existing = ChannelTemplateService.get(db, model=model, key=k)
        if existing is not None:
            raise ChannelTemplateError(f"Template key already exists: {k}")
        row = model(template_key=k, name=(name or k).strip(), body=body or "", is_enabled=bool(is_enabled))
        now = datetime.utcnow()
        row.created_at = now
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def upsert(db: Session, *, model, key: str, name: str, body: str, is_enabled: bool = True):
        k = ChannelTemplateService.normalize_key(key)
        row = ChannelTemplateService.get(db, model=model, key=k)
        if row is None:
            return ChannelTemplateService.create(db, model=model, key=k, name=name, body=body, is_enabled=is_enabled)
        row.name = (name or row.name or k).strip()
        row.body = body or ""
        row.is_enabled = bool(is_enabled)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete(db: Session, *, model: Type, key: str) -> None:
        row = ChannelTemplateService.get(db, model=model, key=key)
        if row is None:
            raise ChannelTemplateError("Template not found")
        db.delete(row)
        db.commit()
