from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.abuu.core.auth import (
    authenticate_driver,
    authenticate_restaurant,
    create_abuu_token,
)
from app.core.abuu_database import get_abuu_db

router = APIRouter(prefix="/abuu/auth", tags=["abuu-auth"])


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
