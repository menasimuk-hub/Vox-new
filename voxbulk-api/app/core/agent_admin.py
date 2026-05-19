from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import require_platform_admin, resolve_admin_role
from app.core.database import get_db
from app.models.user import User


def require_agent_admin(user: User = Depends(require_platform_admin), db: Session = Depends(get_db)) -> User:
    role = resolve_admin_role(db, user)
    if role in {"superadmin", "technical"}:
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent management requires superadmin or technical admin")
