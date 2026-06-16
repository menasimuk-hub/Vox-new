from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.abuu.core.auth import (
    DriverPrincipal,
    RestaurantPrincipal,
    authenticate_driver,
    authenticate_restaurant,
    create_abuu_token,
    require_driver_user,
    require_restaurant_user,
)
from app.core.abuu_database import get_abuu_db

router = APIRouter(prefix="/abuu/auth", tags=["abuu-auth"])


@router.post("/restaurant/logout")
def restaurant_logout(
    principal: RestaurantPrincipal = Depends(require_restaurant_user),
):
    return {"ok": True, "restaurant_id": principal.restaurant_id}


@router.post("/driver/logout")
def driver_logout(
    principal: DriverPrincipal = Depends(require_driver_user),
    db: Session = Depends(get_abuu_db),
):
    from app.abuu.models.entities import Driver

    row = db.get(Driver, principal.driver_id)
    if row is not None:
        row.is_available = False
        db.add(row)
        db.commit()
    return {"ok": True, "driver_id": principal.driver_id, "is_available": False}


@router.post("/restaurant/token")
def restaurant_token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_abuu_db)):
    row = authenticate_restaurant(db, form.username, form.password)
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_abuu_token(subject=row.login_email or row.id, token_type="abuu_restaurant", scope_id=row.id)
    return {"access_token": token, "token_type": "bearer", "restaurant_id": row.id}


@router.post("/driver/token")
def driver_token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_abuu_db)):
    row = authenticate_driver(db, form.username, form.password)
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_abuu_token(subject=row.login_email or row.id, token_type="abuu_driver", scope_id=row.id)
    return {"access_token": token, "token_type": "bearer", "driver_id": row.id}
