"""JWT auth for Abuu restaurant and driver portals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.abuu_database import get_abuu_db
from app.core.security import verify_password
from app.abuu.models.entities import Driver, Restaurant

abuu_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/abuu/auth/restaurant/token", auto_error=True)


def create_abuu_token(*, subject: str, token_type: str, scope_id: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": token_type,
        "scope_id": scope_id,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_abuu_token(token: str, expected_type: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials") from exc
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    if not payload.get("scope_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return payload


@dataclass(frozen=True)
class RestaurantPrincipal:
    restaurant_id: str
    email: str


@dataclass(frozen=True)
class DriverPrincipal:
    driver_id: str
    email: str


def authenticate_restaurant(db: Session, email: str, password: str) -> Restaurant | None:
    row = db.execute(
        select(Restaurant).where(
            Restaurant.login_email == email.strip().lower(),
            Restaurant.is_deleted.is_(False),
            Restaurant.status == "active",
        )
    ).scalar_one_or_none()
    if row is None or not row.password_hash or not verify_password(password, row.password_hash):
        return None
    return row


def authenticate_driver(db: Session, email: str, password: str) -> Driver | None:
    row = db.execute(
        select(Driver).where(
            Driver.login_email == email.strip().lower(),
            Driver.is_deleted.is_(False),
            Driver.status == "active",
        )
    ).scalar_one_or_none()
    if row is None or not row.password_hash or not verify_password(password, row.password_hash):
        return None
    return row


def require_restaurant_user(
    db: Session = Depends(get_abuu_db),
    token: str = Depends(abuu_oauth2_scheme),
) -> RestaurantPrincipal:
    payload = _decode_abuu_token(token, "abuu_restaurant")
    restaurant = db.get(Restaurant, str(payload["scope_id"]))
    if restaurant is None or restaurant.is_deleted or restaurant.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Restaurant access denied")
    return RestaurantPrincipal(restaurant_id=restaurant.id, email=restaurant.login_email or "")


def require_driver_user(
    db: Session = Depends(get_abuu_db),
    token: str = Depends(abuu_oauth2_scheme),
) -> DriverPrincipal:
    payload = _decode_abuu_token(token, "abuu_driver")
    driver = db.get(Driver, str(payload["scope_id"]))
    if driver is None or driver.is_deleted or driver.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Driver access denied")
    return DriverPrincipal(driver_id=driver.id, email=driver.login_email or "")
