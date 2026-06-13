from __future__ import annotations

from fastapi import APIRouter

from app.abuu.routers.health import router as health_router

router = APIRouter()
router.include_router(health_router)
