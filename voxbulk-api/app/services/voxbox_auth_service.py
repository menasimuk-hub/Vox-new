"""Voxbox auth — single admin from .env (bootstrapped into DB, changeable in Settings)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.models.voxbox_admin_user import VoxboxAdminUser

_bearer = HTTPBearer(auto_error=False)
VOXBOX_TOKEN_TYPE = "voxbox"

# voxbulk-api/.env — prefer on-disk values over stale process env after systemd reload.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class VoxboxAuthError(RuntimeError):
    pass


def _strip_env_value(raw: str) -> str:
    v = (raw or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        v = v[1:-1]
    return v.strip()


def _read_env_file_keys(*keys: str) -> dict[str, str]:
    """Last assignment per key in voxbulk-api/.env (same rule as typical dotenv)."""
    out: dict[str, str] = {}
    if not _ENV_FILE.is_file():
        return out
    try:
        text = _ENV_FILE.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out
    wanted = set(keys)
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if key in wanted:
            out[key] = _strip_env_value(val)
    return out


def live_voxbox_admin_creds() -> tuple[str, str, str]:
    """Username / password / display name for Voxbox admin.

    Prefer the on-disk `.env` file. systemd `reload` (HUP) recycles gunicorn workers
    but keeps the master process environment from the first `source .env`, so
    `os.environ` / cached Settings can lag behind edits to `.env`.
    """
    file_vals = _read_env_file_keys(
        "VOXBOX_ADMIN_USERNAME",
        "VOXBOX_ADMIN_PASSWORD",
        "VOXBOX_ADMIN_DISPLAY_NAME",
    )
    settings = get_settings()
    user = (
        file_vals.get("VOXBOX_ADMIN_USERNAME")
        or os.getenv("VOXBOX_ADMIN_USERNAME")
        or settings.voxbox_admin_username
        or "admin"
    ).strip() or "admin"
    password = (
        file_vals.get("VOXBOX_ADMIN_PASSWORD")
        if "VOXBOX_ADMIN_PASSWORD" in file_vals
        else None
    )
    if password is None:
        password = (os.getenv("VOXBOX_ADMIN_PASSWORD") or settings.voxbox_admin_password or "").strip()
    else:
        password = password.strip()
    display = (
        file_vals.get("VOXBOX_ADMIN_DISPLAY_NAME")
        or os.getenv("VOXBOX_ADMIN_DISPLAY_NAME")
        or settings.voxbox_admin_display_name
        or "Admin"
    ).strip() or "Admin"
    return user, password, display


class VoxboxAuthService:
    @staticmethod
    def ensure_admin_row(db: Session) -> VoxboxAdminUser:
        env_user, env_pass, env_display = live_voxbox_admin_creds()
        row = db.get(VoxboxAdminUser, 1)

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

        # Keep DB in sync with .env whenever password is set there (ops source of truth).
        if env_pass:
            needs = (
                (row.username or "").strip() != env_user
                or not (row.password_hash or "").strip()
                or not verify_password(env_pass, row.password_hash)
            )
            if needs:
                row.username = env_user
                row.password_hash = hash_password(env_pass)
                if env_display:
                    row.display_name = env_display
                row.updated_at = datetime.utcnow()
                db.add(row)
                db.commit()
                db.refresh(row)
        elif not (row.password_hash or "").strip():
            raise VoxboxAuthError(
                "Voxbox admin password missing. Set VOXBOX_ADMIN_PASSWORD in .env"
            )
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
            # Fallback: allow live .env credentials if DB was out of sync
            env_user, env_pass, _ = live_voxbox_admin_creds()
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
            _, env_pass, _ = live_voxbox_admin_creds()
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
