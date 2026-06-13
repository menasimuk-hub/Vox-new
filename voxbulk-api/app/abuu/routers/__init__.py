from __future__ import annotations

from fastapi import APIRouter

from app.abuu.routers.admin import router as admin_router
from app.abuu.routers.auth import router as auth_router
from app.abuu.routers.driver import router as driver_router
from app.abuu.routers.health import router as health_router
from app.abuu.routers.restaurant import router as restaurant_router

router = APIRouter()
router.include_router(health_router)
router.include_router(admin_router)
router.include_router(auth_router)
router.include_router(restaurant_router)
router.include_router(driver_router)
