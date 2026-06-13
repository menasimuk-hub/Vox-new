"""Restaurant and driver JWT auth — implemented in Phase 2."""

from __future__ import annotations

from fastapi import HTTPException, status


def require_restaurant_user():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Restaurant auth is not available until Abuu Phase 2",
    )


def require_driver_user():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Driver auth is not available until Abuu Phase 2",
    )
