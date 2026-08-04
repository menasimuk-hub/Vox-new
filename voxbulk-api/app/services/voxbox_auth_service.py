"""Voxbox auth — single admin from .env (bootstrapped into DB, changeable in Settings)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models.voxbox_admin_user import VoxboxAdminUser

_bearer = HTTPBearer(auto_error=False)
VOXBOX_TOKEN_TYPE = "voxbox"


class VoxboxAuthError(RuntimeError):
    pass


class VoxboxAuthService:
    @staticmethod
    def ensure_admin_row(db: Session) -> VoxboxAdminUser:
        settings = get_settings()
        row = db.get(VoxboxAdminUser, 1)
        env_user = (settings.voxbox_admin_username or "admin").strip() or "admin"
        env_pass = (settings.voxbox_admin_password or "").strip()
        env_display = (settings.voxbox_admin_display_name or "Admin").strip() or "Admin"

        if row is None:
            if not env_pass:
                raise VoxboxAuthError(
                    "Voxbox admin is not configured. Set VOXBOX_ADMIN_USERNAME and VOXBOX_ADMIN_PASSWORD in .env"
                )
            row = VoxboxAdminUser(
                id=1,
                username=env_user,
                password_hash=hash_password(env_pass),
                display_name=env_display,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row

        # If DB password empty (corrupt), re-seed from env when available.
        if not (row.password_hash or "").strip() and env_pass:
            row.username = env_user
            row.password_hash = hash_password(env_pass)
            row.display_name = env_display or row.display_name
            row.updated_at = datetime.utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def create_token(*, username: str, display_name: str) -> str:
        settings = get_settings()
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
        payload: dict[str, Any] = {
            "sub": username,
            "display_name": display_name,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": VOXBOX_TOKEN_TYPE,
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def login(db: Session, *, username: str, password: str) -> dict[str, Any]:
        row = VoxboxAuthService.ensure_admin_row(db)
        user = (username or "").strip()
        if user != (row.username or "").strip() or not verify_password(password, row.password_hash):
            # Fallback: allow env credentials once if DB was seeded differently
            settings = get_settings()
            env_user = (settings.voxbox_admin_username or "").strip()
            env_pass = (settings.voxbox_admin_password or "").strip()
            if not (env_user and env_pass and user == env_user and password == env_pass):
                raise VoxboxAuthError("Invalid username or password")
            row.username = env_user
            row.password_hash = hash_password(env_pass)
            row.updated_at = datetime.utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)

        token = VoxboxAuthService.create_token(username=row.username, display_name=row.display_name)
        return {
            "access_token": token,
            "token_type": "bearer",
            "username": row.username,
            "display_name": row.display_name,
        }

    @staticmethod
    def me(db: Session, *, username: str) -> dict[str, str]:
        row = VoxboxAuthService.ensure_admin_row(db)
        if (row.username or "").strip() != (username or "").strip():
            raise VoxboxAuthError("Unauthorized")
        return {"username": row.username, "display_name": row.display_name}

    @staticmethod
    def update_credentials(
        db: Session,
        *,
        username: str,
        current_password: str,
        new_username: str | None = None,
        new_password: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, str]:
        row = VoxboxAuthService.ensure_admin_row(db)
        if (row.username or "").strip() != (username or "").strip():
            raise VoxboxAuthError("Unauthorized")
        if not verify_password(current_password, row.password_hash):
            settings = get_settings()
            env_pass = (settings.voxbox_admin_password or "").strip()
            if not (env_pass and current_password == env_pass):
                raise VoxboxAuthError("Current password is incorrect")

        if new_username is not None and str(new_username).strip():
            row.username = str(new_username).strip()[:120]
        if new_password is not None and str(new_password).strip():
            if len(str(new_password).strip()) < 8:
                raise VoxboxAuthError("New password must be at least 8 characters")
            row.password_hash = hash_password(str(new_password).strip())
        if display_name is not None and str(display_name).strip():
            row.display_name = str(display_name).strip()[:120]
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"username": row.username, "display_name": row.display_name}


def get_voxbox_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    settings = get_settings()
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    if payload.get("type") != VOXBOX_TOKEN_TYPE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    username = str(payload.get("sub") or "").strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        return VoxboxAuthService.me(db, username=username)
    except VoxboxAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
